//! Owner-scoped, resumable exact search. / 按所有者隔离、可续扫的精确检索。

use std::collections::HashMap;

use super::*;

const JOB_TTL_MS: i64 = 24 * 60 * 60 * 1000;
const JOB_LEASE_MS: i64 = 2 * 60 * 1000;
const JOB_LIMIT: i64 = 5;
const JOB_TOTAL_LIMIT: i64 = 256;

/// Bound scans that require Rust text/vector filtering; indexed newest/mailbox/date/read lists stay write-free. / 限制需由 Rust 逐条文本或向量筛选的扫描；可索引的最新/邮箱/日期/已读列表保持无写入。
fn expensive(input: &SearchRequest) -> bool {
    input.semantic.is_some()
        || input.body.is_some()
        || input.title.is_some()
        || input.from.is_some()
        || input.to.is_some()
        || input.metadata.as_ref().is_some_and(|map| !map.is_empty())
}

/// Atomically admit one broad-filter request against account and shared daily budgets. / 按账户与共享每日额度原子准入一次宽泛筛选请求。
async fn reserve_search_work(database: &D1Database, user: &Principal) -> AppResult<()> {
    let quota = |error: AppError| {
        if error.status == 429 {
            AppError {
                status: 429,
                code: "search_work_quota",
            }
        } else {
            error
        }
    };
    reserve_quota(database, "search_work", user, 1, 300)
        .await
        .map_err(quota)?;
    let global = Principal {
        iss: "_global".into(),
        sub: "_global".into(),
    };
    reserve_quota(database, "search_work_global", &global, 1, 20_000)
        .await
        .map_err(quota)?;
    Ok(())
}

/// Read the mutation generation that protects a multi-invocation result. / 读取保护跨调用结果的变更代际。
async fn generation(database: &D1Database, user: &Principal) -> AppResult<i64> {
    let row = database
        .prepare("SELECT generation FROM search_generations WHERE owner_iss=?1 AND owner_sub=?2")
        .bind(&[bind_str(&user.iss), bind_str(&user.sub)])?
        .first::<SearchGeneration>(None)
        .await?;
    Ok(row.map_or(0, |row| row.generation))
}

/// Bind a cursor to canonical filters, owner, and mutation generation. / 将游标绑定至规范化筛选器、所有者与变更代际。
fn query_hash(input: &SearchRequest, user: &Principal) -> AppResult<String> {
    let mut value = serde_json::to_value(input).map_err(|_| AppError::bad("invalid_search"))?;
    value["cursor"] = serde_json::Value::Null;
    value["limit"] = serde_json::json!(input.limit.unwrap_or(20));
    value["regex"] = serde_json::json!(input.regex.unwrap_or(false));
    value["case_sensitive"] = serde_json::json!(input.case_sensitive.unwrap_or(false));
    Ok(format!(
        "{:x}",
        Sha256::digest(format!("{}:{}:{value}", user.iss, user.sub).as_bytes())
    ))
}

fn decode_cursor(
    input: &SearchRequest,
    hash: &str,
    generation: i64,
) -> AppResult<Option<SearchCursor>> {
    let Some(encoded) = input.cursor.as_deref() else {
        return Ok(None);
    };
    let bytes = URL_SAFE_NO_PAD
        .decode(encoded)
        .map_err(|_| AppError::bad("invalid_cursor"))?;
    let cursor: SearchCursor =
        serde_json::from_slice(&bytes).map_err(|_| AppError::bad("invalid_cursor"))?;
    if cursor.version != 3
        || cursor.hash != hash
        || cursor.high_water > now() + 60_000
        || cursor.last_time >= cursor.high_water
        || cursor.last_id.is_empty()
        || cursor.last_score_bits.is_some() != input.semantic.is_some()
        || cursor
            .last_score_bits
            .is_some_and(|bits| !f64::from_bits(bits).is_finite())
    {
        return Err(AppError::bad("invalid_cursor"));
    }
    if cursor.generation != generation {
        return Err(AppError::conflict("search_cursor_stale"));
    }
    Ok(Some(cursor))
}

fn dates(input: &SearchRequest) -> AppResult<(Option<i64>, Option<i64>)> {
    let after = input
        .after
        .as_deref()
        .map(parse_date)
        .transpose_option()
        .ok_or_else(|| AppError::bad("invalid_date"))?;
    let before = input
        .before
        .as_deref()
        .map(parse_date)
        .transpose_option()
        .ok_or_else(|| AppError::bad("invalid_date"))?;
    if after.zip(before).is_some_and(|(a, b)| a >= b) {
        return Err(AppError::bad("invalid_date_range"));
    }
    Ok((after, before))
}

fn running(id: &str, request_id: &str) -> AppResult<Response> {
    Ok(Response::from_json(&serde_json::json!({
        "job_id":id,"state":"running","retry_after_ms":500,"request_id":request_id
    }))?
    .with_status(202))
}

fn stale() -> AppError {
    AppError::conflict("search_job_stale")
}

/// Start an exact search. Fast scans answer immediately; longer scans return a durable job ID. / 启动精确检索：快扫描直接应答，长扫描返回持久任务 ID。
pub(super) async fn search(
    env: &Env,
    user: &Principal,
    input: SearchRequest,
    request_id: &str,
) -> AppResult<Response> {
    let limit = input.limit.unwrap_or(20);
    if !(1..=100).contains(&limit) {
        return Err(AppError::bad("invalid_limit"));
    }
    dates(&input)?;
    SearchMatcher::new(&input)?;
    let request_json =
        serde_json::to_string(&input).map_err(|_| AppError::bad("invalid_search"))?;
    if request_json.len() > 8192 {
        return Err(AppError::bad("search_request_too_large"));
    }
    let database = db(env)?;
    let epoch = generation(&database, user).await?;
    let hash = query_hash(&input, user)?;
    let cursor = decode_cursor(&input, &hash, epoch)?;
    let semantic = input.semantic.is_some();
    let mut state = SearchState {
        high_water: cursor.as_ref().map_or_else(|| now() + 1, |c| c.high_water),
        generation: epoch,
        marker: if semantic {
            None
        } else {
            cursor.as_ref().map(|c| (c.last_time, c.last_id.clone()))
        },
        hits: Vec::new(),
        query_vector: None,
        query_model: None,
    };
    if !semantic && expensive(&input) {
        reserve_search_work(&database, user).await?;
    }
    // Most list/lexical searches finish without writing a job. Only continuation is durable.
    // 多数列表/词法检索无需写入任务；仅在确实需要续扫时持久化。
    if !semantic {
        let first_marker = state.marker.clone();
        let complete = scan_batch(&database, user, &input, &mut state, cursor.as_ref()).await?;
        if complete {
            let result = result_page(&database, user, &input, &state, &hash, request_id).await?;
            if generation(&database, user).await? != epoch {
                return Err(stale());
            }
            return Ok(Response::from_json(&result)?);
        }
        if state.marker == first_marker {
            return Err(search_resource_limit());
        }
    }
    #[derive(Deserialize)]
    struct JobCounts {
        active: i64,
        total: i64,
    }
    // Reject ordinary over-quota calls before spending an OpenRouter embedding request.
    // 常见超额请求在消耗 OpenRouter 向量计算前拒绝；后续 INSERT 仍负责原子校验。
    let counts = database
        .prepare("SELECT COALESCE(SUM(CASE WHEN state IN ('preparing','running','advancing') THEN 1 ELSE 0 END),0) AS active,COUNT(*) AS total FROM search_jobs WHERE owner_iss=?1 AND owner_sub=?2 AND state IN ('preparing','running','advancing','done','stale') AND expires_at>?3")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_num(now())])?
        .first::<JobCounts>(None)
        .await?;
    if counts.is_some_and(|counts| counts.active >= JOB_LIMIT || counts.total >= JOB_TOTAL_LIMIT) {
        return Err(AppError {
            status: 429,
            code: "search_job_quota",
        });
    }
    let id = uuid::Uuid::new_v4().to_string();
    let created = now();
    let inserted = database
        .prepare("INSERT INTO search_jobs(id,owner_iss,owner_sub,request_json,state_json,state,created_at,expires_at) SELECT ?1,?2,?3,?4,?5,?6,?7,?8 WHERE (SELECT COUNT(*) FROM search_jobs WHERE owner_iss=?2 AND owner_sub=?3 AND state IN ('preparing','running','advancing') AND expires_at>?7)<?9 AND (SELECT COUNT(*) FROM search_jobs WHERE owner_iss=?2 AND owner_sub=?3 AND state IN ('preparing','running','advancing','done','stale') AND expires_at>?7)<?10 AND COALESCE((SELECT generation FROM search_generations WHERE owner_iss=?2 AND owner_sub=?3),0)=?11")
        .bind(&[
            bind_str(&id), bind_str(&user.iss), bind_str(&user.sub), bind_str(&request_json),
            bind_str(&serde_json::to_string(&state).map_err(|_| AppError::bad("invalid_search"))?),
            bind_str(if semantic {"preparing"} else {"running"}), bind_num(created), bind_num(created + JOB_TTL_MS), bind_num(JOB_LIMIT), bind_num(JOB_TOTAL_LIMIT),bind_num(epoch),
        ])?
        .run()
        .await?;
    if inserted.meta()?.and_then(|meta| meta.changes).unwrap_or(0) != 1 {
        if generation(&database, user).await? != epoch {
            return Err(stale());
        }
        return Err(AppError {
            status: 429,
            code: "search_job_quota",
        });
    }
    if !semantic {
        return running(&id, request_id);
    }
    if let Some(term) = input.semantic.as_deref() {
        let prepared: AppResult<()> = async {
            // Reserve the D1 slot and daily provider budget before any billable call.
            // 任何可计费调用之前，先原子预留 D1 任务槽和每日供应商额度。
            reserve_search_work(&database, user).await?;
            reserve_quota(&database, "semantic_queries", user, 1, 500)
                .await
                .map_err(|error| if error.status == 429 { AppError { status:429, code:"semantic_quota" } } else { error })?;
            let global = Principal { iss:"_global".into(), sub:"_global".into() };
            reserve_quota(&database, "semantic_queries_global", &global, 1, 50_000)
                .await
                .map_err(|error| if error.status == 429 { AppError { status:429, code:"semantic_quota" } } else { error })?;
            state.query_vector = Some(platform::embed(env, term, "search_query").await.map_err(|_| AppError {
                status:503, code:"semantic_unavailable"
            })?);
            state.query_model = Some(env.var("OPENROUTER_EMBEDDING_MODEL")
                .map_err(|_| AppError { status:503, code:"semantic_unavailable" })?.to_string());
            let serialized = serde_json::to_string(&state).map_err(|_| AppError::bad("invalid_search"))?;
            let changed = database.prepare("UPDATE search_jobs SET state='running',state_json=?1 WHERE id=?2 AND owner_iss=?3 AND owner_sub=?4 AND state='preparing'")
                .bind(&[bind_str(&serialized),bind_str(&id),bind_str(&user.iss),bind_str(&user.sub)])?
                .run().await?.meta()?.and_then(|meta|meta.changes).unwrap_or(0);
            if changed != 1 {
                return Err(AppError { status:503, code:"search_job_prepare_unknown" });
            }
            Ok(())
        }.await;
        if let Err(error) = prepared {
            if let Ok(query) = database.prepare("DELETE FROM search_jobs WHERE id=?1 AND owner_iss=?2 AND owner_sub=?3 AND state='preparing'")
                .bind(&[bind_str(&id),bind_str(&user.iss),bind_str(&user.sub)])
            {
                let _ = query.run().await;
            }
            return Err(error);
        }
    }
    let result = advance(env, user, &id, request_id).await;
    match result {
        Ok((response, completed)) => {
            if completed {
                // A fast POST never exposed its job ID; retain no query copy after its response.
                // 快速 POST 不暴露任务 ID；应答后不保留查询副本。
                let _ = database
                    .prepare("DELETE FROM search_jobs WHERE id=?1")
                    .bind(&[bind_str(&id)])?
                    .run()
                    .await;
            }
            Ok(response)
        }
        Err(error) => {
            let _ = database
                .prepare("DELETE FROM search_jobs WHERE id=?1")
                .bind(&[bind_str(&id)])?
                .run()
                .await;
            Err(error)
        }
    }
}

/// Resume one owner-scoped batch; a replay of a completed poll returns its original result. / 续扫一个所有者批次；已完成轮询的重放返回同一结果。
pub(super) async fn poll(
    env: &Env,
    user: &Principal,
    id: &str,
    request_id: &str,
) -> AppResult<Response> {
    if uuid::Uuid::parse_str(id).is_err() {
        return Err(AppError::not_found());
    }
    advance(env, user, id, request_id)
        .await
        .map(|(response, _)| response)
}

async fn load_job(database: &D1Database, user: &Principal, id: &str) -> AppResult<SearchJobRow> {
    database
        .prepare("SELECT id,request_json,state_json,state,version,lease_started_at,expires_at,COALESCE((SELECT generation FROM search_generations WHERE owner_iss=search_jobs.owner_iss AND owner_sub=search_jobs.owner_sub),0) AS current_generation FROM search_jobs WHERE id=?1 AND owner_iss=?2 AND owner_sub=?3")
        .bind(&[bind_str(id), bind_str(&user.iss), bind_str(&user.sub)])?
        .first::<SearchJobRow>(None)
        .await?
        .ok_or_else(AppError::not_found)
}

async fn claim(
    database: &D1Database,
    user: &Principal,
    id: &str,
) -> AppResult<Option<SearchJobRow>> {
    let mut row = load_job(database, user, id).await?;
    if row.expires_at <= now() {
        return Err(AppError {
            status: 410,
            code: "search_job_expired",
        });
    }
    if row.state == "stale" {
        return Err(stale());
    }
    if row.state == "done" {
        return Ok(Some(row));
    }
    if row.state == "advancing" {
        if row
            .lease_started_at
            .is_some_and(|started| started > now() - JOB_LEASE_MS)
        {
            return Ok(None);
        }
        database
            .prepare("UPDATE search_jobs SET state='running',version=version+1,lease_started_at=NULL WHERE id=?1 AND owner_iss=?2 AND owner_sub=?3 AND state='advancing' AND version=?4 AND lease_started_at<?5")
            .bind(&[bind_str(id),bind_str(&user.iss),bind_str(&user.sub),bind_num(row.version),bind_num(now()-JOB_LEASE_MS)])?
            .run().await?;
        row = load_job(database, user, id).await?;
    }
    if row.state != "running" {
        return Ok(None);
    }
    let changed = database
        .prepare("UPDATE search_jobs SET state='advancing',version=version+1,lease_started_at=?1 WHERE id=?2 AND owner_iss=?3 AND owner_sub=?4 AND state='running' AND version=?5")
        .bind(&[bind_num(now()),bind_str(id),bind_str(&user.iss),bind_str(&user.sub),bind_num(row.version)])?
        .run().await?
        .meta()?.and_then(|meta| meta.changes).unwrap_or(0);
    if changed != 1 {
        return Ok(None);
    }
    row.version += 1;
    Ok(Some(row))
}

async fn release(database: &D1Database, id: &str, version: i64, error: &AppError) {
    let sql = if matches!(error.code, "search_job_stale" | "search_resource_limit") {
        "UPDATE search_jobs SET state='stale',request_json='{}',state_json='{}',version=version+1,lease_started_at=NULL WHERE id=?1 AND state='advancing' AND version=?2"
    } else {
        "UPDATE search_jobs SET state='running',version=version+1,lease_started_at=NULL WHERE id=?1 AND state='advancing' AND version=?2"
    };
    if let Ok(query) = database
        .prepare(sql)
        .bind(&[bind_str(id), bind_num(version)])
    {
        let _ = query.run().await;
    }
}

async fn scrub_done(database: &D1Database, id: &str, version: i64) {
    if let Ok(query) = database
        .prepare("UPDATE search_jobs SET state='stale',request_json='{}',state_json='{}',version=version+1 WHERE id=?1 AND state='done' AND version=?2")
        .bind(&[bind_str(id),bind_num(version)])
    {
        let _ = query.run().await;
    }
}

async fn advance(
    env: &Env,
    user: &Principal,
    id: &str,
    request_id: &str,
) -> AppResult<(Response, bool)> {
    let database = db(env)?;
    let Some(row) = claim(&database, user, id).await? else {
        return Ok((running(id, request_id)?, false));
    };
    if row.state == "done" {
        let input: SearchRequest = serde_json::from_str(&row.request_json).map_err(|_| stale())?;
        let state: SearchState = serde_json::from_str(&row.state_json).map_err(|_| stale())?;
        if row.current_generation != state.generation {
            scrub_done(&database, id, row.version).await;
            return Err(stale());
        }
        let hash = query_hash(&input, user)?;
        let result = match result_page(&database, user, &input, &state, &hash, request_id).await {
            Ok(result) => result,
            Err(error) if error.code == "search_job_stale" => {
                scrub_done(&database, id, row.version).await;
                return Err(error);
            }
            Err(error) => return Err(error),
        };
        if generation(&database, user).await? != state.generation {
            scrub_done(&database, id, row.version).await;
            return Err(stale());
        }
        return Ok((Response::from_json(&result)?, true));
    }
    let work = advance_claimed(&database, user, &row, request_id).await;
    if let Err(error) = &work {
        release(&database, id, row.version, error).await;
    }
    work
}

async fn advance_claimed(
    database: &D1Database,
    user: &Principal,
    row: &SearchJobRow,
    request_id: &str,
) -> AppResult<(Response, bool)> {
    let input: SearchRequest = serde_json::from_str(&row.request_json).map_err(|_| stale())?;
    let mut state: SearchState = serde_json::from_str(&row.state_json).map_err(|_| stale())?;
    if generation(database, user).await? != state.generation {
        return Err(stale());
    }
    let hash = query_hash(&input, user)?;
    let cursor = decode_cursor(&input, &hash, state.generation)?;
    let previous_marker = state.marker.clone();
    let complete = scan_batch(database, user, &input, &mut state, cursor.as_ref()).await?;
    if !complete && state.marker == previous_marker {
        return Err(AppError {
            status: 422,
            code: "search_resource_limit",
        });
    }
    if generation(database, user).await? != state.generation {
        return Err(stale());
    }
    if complete {
        let result = result_page(database, user, &input, &state, &hash, request_id).await?;
        if generation(database, user).await? != state.generation {
            return Err(stale());
        }
        state.query_vector = None;
        let serialized = serde_json::to_string(&state).map_err(|_| stale())?;
        let changed = database
            .prepare("UPDATE search_jobs SET state='done',state_json=?1,version=version+1,lease_started_at=NULL WHERE id=?2 AND owner_iss=?3 AND owner_sub=?4 AND state='advancing' AND version=?5 AND COALESCE((SELECT generation FROM search_generations WHERE owner_iss=?3 AND owner_sub=?4),0)=?6")
            .bind(&[bind_str(&serialized),bind_str(&row.id),bind_str(&user.iss),bind_str(&user.sub),bind_num(row.version),bind_num(state.generation)])?
            .run().await?.meta()?.and_then(|meta| meta.changes).unwrap_or(0);
        if changed != 1 {
            return Err(stale());
        }
        return Ok((Response::from_json(&result)?, true));
    }
    let serialized = serde_json::to_string(&state).map_err(|_| stale())?;
    let changed = database
        .prepare("UPDATE search_jobs SET state_json=?1,state='running',version=version+1,lease_started_at=NULL WHERE id=?2 AND owner_iss=?3 AND owner_sub=?4 AND state='advancing' AND version=?5 AND COALESCE((SELECT generation FROM search_generations WHERE owner_iss=?3 AND owner_sub=?4),0)=?6")
        .bind(&[bind_str(&serialized),bind_str(&row.id),bind_str(&user.iss),bind_str(&user.sub),bind_num(row.version),bind_num(state.generation)])?
        .run().await?.meta()?.and_then(|meta| meta.changes).unwrap_or(0);
    if changed != 1 {
        return Err(stale());
    }
    Ok((running(&row.id, request_id)?, false))
}

/// One invocation examines an ordered prefix, checkpointing only fully processed rows. / 每次调用扫描一个有序前缀，只检查点化完整处理过的记录。
async fn scan_batch(
    database: &D1Database,
    user: &Principal,
    input: &SearchRequest,
    state: &mut SearchState,
    cursor: Option<&SearchCursor>,
) -> AppResult<bool> {
    let matcher = SearchMatcher::new(input)?;
    let (after, before) = dates(input)?;
    let limit = input.limit.unwrap_or(20);
    let semantic = input.semantic.is_some();
    let mut calls = 0usize;
    let mut transfer = 0usize;
    let mut body_bytes = 0usize;
    let started = now();
    loop {
        if search_budget_exceeded(calls, transfer, body_bytes) || now() - started >= 20_000 {
            return Ok(false);
        }
        let (query, binds) = search_page_query(
            input,
            user,
            after,
            before,
            state.high_water,
            state.marker.as_ref(),
        );
        let page = database
            .prepare(&query)
            .bind(&binds)?
            .all()
            .await?
            .results::<MessageRow>()?;
        calls += 1;
        let page_len = page.len();
        for mut row in page {
            transfer = transfer.saturating_add(
                row.subject.len()
                    + row.sender.len()
                    + row.recipients_json.len()
                    + row.metadata_json.len()
                    + row.body_text.len()
                    + row.embedding_json.as_ref().map_or(0, String::len),
            );
            if search_budget_exceeded(0, transfer, body_bytes) {
                return Ok(false);
            }
            let row_marker = (row.received_at, row.id.clone());
            if !matcher.matches_without_body(&row) {
                state.marker = Some(row_marker);
                continue;
            }
            if matcher.has_body() {
                let text = match full_text(database, &row, &mut calls, body_bytes).await {
                    Ok(text) => text,
                    Err(error) if error.code == "search_resource_limit" => return Ok(false),
                    Err(error) => return Err(error),
                };
                body_bytes = body_bytes.saturating_add(text.len());
                if !matcher.matches_body(&text) {
                    state.marker = Some(row_marker);
                    continue;
                }
                row.body_text.clear();
            }
            let score = if let Some(query) = state.query_vector.as_ref() {
                // A model/configuration transition must fail closed rather than
                // compare vectors from different spaces. Old jobs without a model
                // checkpoint are explicitly incomplete and can be restarted.
                if !semantic_document_compatible(&row, state.query_model.as_deref()) {
                    return Err(AppError {
                        status: 503,
                        code: "semantic_index_incomplete",
                    });
                }
                let saved = row.embedding_json.as_deref().ok_or(AppError {
                    status: 503,
                    code: "semantic_index_incomplete",
                })?;
                let vector: Vec<f32> = serde_json::from_str(saved).map_err(|_| AppError {
                    status: 503,
                    code: "semantic_index_corrupt",
                })?;
                Some(cosine_exact(query, &vector).ok_or(AppError {
                    status: 503,
                    code: "semantic_index_corrupt",
                })?)
            } else {
                None
            };
            if let (Some(previous), Some(score)) = (cursor, score) {
                let previous_score = f64::from_bits(previous.last_score_bits.unwrap_or_default());
                if semantic_rank(
                    (score, row.received_at, &row.id),
                    (previous_score, previous.last_time, &previous.last_id),
                ) != std::cmp::Ordering::Greater
                {
                    state.marker = Some(row_marker);
                    continue;
                }
            }
            let hit = SearchHit {
                id: row.id,
                time: row.received_at,
                score_bits: score.map(f64::to_bits),
            };
            if semantic {
                retain_semantic(&mut state.hits, hit, limit + 1, SearchHit::rank);
            } else {
                state.hits.push(hit);
            }
            state.marker = Some(row_marker);
            if !semantic && state.hits.len() > limit {
                return Ok(true);
            }
        }
        if page_len < search_page_size(input) {
            return Ok(true);
        }
    }
}

async fn result_page(
    database: &D1Database,
    user: &Principal,
    input: &SearchRequest,
    state: &SearchState,
    hash: &str,
    request_id: &str,
) -> AppResult<serde_json::Value> {
    let mut hits = state.hits.clone();
    if input.semantic.is_some() {
        hits.sort_by(|a, b| semantic_rank(a.rank(), b.rank()));
    }
    let limit = input.limit.unwrap_or(20);
    let has_more = hits.len() > limit;
    hits.truncate(limit);
    let next_cursor = if has_more {
        let last = hits.last().ok_or_else(stale)?;
        let cursor = SearchCursor {
            version: 3,
            hash: hash.to_owned(),
            high_water: state.high_water,
            generation: state.generation,
            last_time: last.time,
            last_id: last.id.clone(),
            last_score_bits: last.score_bits,
        };
        Some(URL_SAFE_NO_PAD.encode(serde_json::to_vec(&cursor).map_err(|_| stale())?))
    } else {
        None
    };
    let mut rows = HashMap::new();
    for chunk in hits.chunks(40) {
        let mut query = search_summary_projection().to_owned();
        query.push_str(" AND id IN (");
        query.push_str(
            &(0..chunk.len())
                .map(|index| format!("?{}", index + 3))
                .collect::<Vec<_>>()
                .join(","),
        );
        query.push(')');
        let mut binds = vec![bind_str(&user.iss), bind_str(&user.sub)];
        binds.extend(chunk.iter().map(|hit| bind_str(&hit.id)));
        for row in database
            .prepare(&query)
            .bind(&binds)?
            .all()
            .await?
            .results::<MessageRow>()?
        {
            rows.insert(row.id.clone(), row);
        }
    }
    let messages = hits
        .iter()
        .map(|hit| {
            rows.get(&hit.id)
                .map(|row| summary(row, hit.score_bits.map(f64::from_bits)))
                .ok_or_else(stale)
        })
        .collect::<AppResult<Vec<_>>>()?;
    Ok(serde_json::json!({"messages":messages,"next_cursor":next_cursor,"request_id":request_id}))
}

/// Expired jobs retain a brief tombstone for a stable 410 before permanent deletion. / 过期任务短暂保留墓碑以稳定返回 410，然后永久清除。
pub(super) async fn cleanup(env: &Env) -> Result<()> {
    let database = env.d1("MAIL_DB")?;
    database
        .prepare("DELETE FROM search_jobs WHERE state='preparing' AND created_at<?1")
        .bind(&[bind_num(now() - 10 * 60_000)])?
        .run()
        .await?;
    // At 24h, discard query text/vector; only an opaque 410 tombstone remains another day.
    // 24 小时后清除查询文本/向量；仅保留一天不透明的 410 墓碑。
    database
        .prepare("UPDATE search_jobs SET state='expired',request_json='{}',state_json='{}' WHERE expires_at<=?1 AND state!='expired'")
        .bind(&[bind_num(now())])?
        .run()
        .await?;
    database
        .prepare("DELETE FROM search_jobs WHERE state='expired' AND expires_at<?1")
        .bind(&[bind_num(now() - JOB_TTL_MS)])?
        .run()
        .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Indexed list predicates stay free of daily write admission; broad Rust filters do not. / 可索引列表谓词免除每日写入准入，宽泛 Rust 过滤则不免除。
    #[test]
    fn expensive_search_classification() {
        assert!(!expensive(&SearchRequest::default()));
        assert!(!expensive(&SearchRequest {
            regex: Some(true),
            ..Default::default()
        }));
        assert!(!expensive(&SearchRequest {
            mailbox: Some("a@mail.moesegfault.dev".into()),
            after: Some("2026-01-01T00:00:00Z".into()),
            read: Some(false),
            ..Default::default()
        }));
        for request in [
            SearchRequest {
                title: Some("x".into()),
                ..Default::default()
            },
            SearchRequest {
                body: Some("x".into()),
                ..Default::default()
            },
            SearchRequest {
                semantic: Some("x".into()),
                ..Default::default()
            },
            SearchRequest {
                from: Some("x".into()),
                regex: Some(true),
                ..Default::default()
            },
            SearchRequest {
                metadata: Some([("message_id".into(), "x".into())].into()),
                ..Default::default()
            },
        ] {
            assert!(expensive(&request));
        }
    }
}
