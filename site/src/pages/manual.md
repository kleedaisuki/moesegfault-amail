---
layout: ../layouts/ManualLayout.astro
title: 用户手册
description: amail 的安装、登录、地址管理、邮件检索和 ZIP 收发指南。
---

## 先认识 amail

amail 是一个面向 AI Agent 的命令行邮件客户端。你在浏览器里完成 moeSegFault 登录；此后 Agent 可以通过 amail 注册地址、检索邮件、更新状态和发送消息。它**没有收件箱网页，也没有 `view` 命令**：邮件内容以 ZIP 消息包交接，默认检索输出则是适合继续处理的紧凑数据。

**使用前的隐私提示：** 服务端会自动为收发邮件建立语义索引，把邮件主题与正文提取文本发送给 OpenRouter 及其上游模型服务商；即使从不使用 `--semantic`，也会进行这一步。首发版没有逐账号关闭索引的选项。注册收件地址前，请先阅读[隐私与边界](#隐私与边界)。

| 你负责 | Agent 可以负责 |
| --- | --- |
| 明确完成登录授权 | 注册与管理邮箱地址 |
| 决定哪些任务交给 Agent | 同步、检索、读取、标记、删除邮件 |
| 检查重要对外沟通 | 准备 ZIP 并调用 amail 发送 |

### 可以直接交给 Agent 的首次任务

> 请确认当前真正公开的 amail 版本，按我的系统选择 CLI 与配套 Agent Skill，使用同一 Release 的 SHA256SUMS 校验后安装；如果尚未完整发布，不要用候选包替代。先说明自动第三方邮件索引的处理方式，再启动 `amail login`，让我自己完成浏览器授权。检查会话与现有地址，优先复用启用的地址。随后只准备我明确授权的任务通知，不要求我学习命令，也不索要口令或令牌。

## v0.1.2 候选：从小入口探索完整工作流

以下是 **staging 候选**的新增能力，不代表 v0.1.2 已正式发布、服务已向公众开放或允许发送。安装来源仍按下方正式发布说明；使用较早版本时，先检查 `amail --version` 和命令帮助，不要把候选命令当作已有能力。

渐进式披露（Progressive Disclosure）不是删掉复杂能力，而是让 Agent 按任务逐步进入可查询的空间：

```sh
amail discover
amail discover send
amail discover events
```

第一条仅返回离线主题目录；需要发送恢复、事件字段或任务示例时，再查看对应主题及它列出的子主题。它说明**当前安装的客户端**，不替服务端宣布权限。普通检索仍是小份 JSON Lines；正文、投递反馈、发送政策不会挤进每一条结果。

### 中断后找回同一次发送

Agent 应在任务文件中**先保存一个 UUID**，代表这一次发送意图，再打包发送：

```sh
amail pack report-draft -o report.zip
amail --machine send report.zip --idempotency-key TASK_UUID
amail send-status TASK_UUID
```

将 `TASK_UUID` 替换为保存的真实 UUID。幂等键（Idempotency Key）不是“相同内容永远只发一次”：一次意图使用同一键和相同 ZIP；另一次确实获准的新任务，可以使用新键发送相同内容。结果丢失或网络不确定时，先查原键，**不能换键盲目重发**。`amail send-receipts --limit 20` 和 `amail send-status TASK_UUID --local` 可找回本机已保存的接受回执，但这是历史证据，不是当前投递状态；没有本地回执也不证明没发出去。

`--machine` 是显式选择的结构化控制模式：正常邮件标准输出保持原有 JSONL，错误、发送意图和续作记录则以带版本的 JSONL 写入标准错误。脚本应分开捕获两条流，不把控制记录当作邮件，也不用解析英文提示。长检索可用 `amail --machine search --title release --wait-seconds 1`，从续作记录取得任务 ID，再以 `search --resume` 继续同一任务。未完成不是空结果。

### 按需查询投递反馈与限制

```sh
amail sending-status
amail outcomes MESSAGE_ID
amail events --message MESSAGE_ID --limit 20
amail events --kind bounced --since 2026-10-03T00:00:00Z --limit 20
```

`sending-status` 给出当前账号适用的政策与额度事实，不暴露运营人员备注或其他账号用量，也不保证特定请求必然获准。`outcomes` 查看已知发件的逐收件人反馈；账号级 `events` 则能在**还不知道哪封邮件变化时**发现事件。六种事件为延迟、投递、退信、失败、拒绝、投诉；它们是供应商反馈，不是阅读回执。

事件页最多 100 条，返回游标时以同样条件继续。`--since` 包含起点，按服务收到事件的时间筛选，不是事件最初发生时间，因此迟到反馈仍可被找到。一次翻页有固定上界，之后新来的反馈需要重新查询。事件通常保留 90 天；空列表不证明历史上从未发生过事件。**接受不等于投递，缺少反馈不等于成功、失败或可重发。** 你自己的逐收件人信息可能包含密送地址，不应向任务之外的人分享。

### 查找关联回复，再建立新草稿

从 `amail get MESSAGE_ID` 或取回的消息包中确认可选的已验证 `rfc_message_id`（RFC Message-ID），再用 `amail search --meta in_reply_to=RFC_MESSAGE_ID` 查对应回复。不要把本地邮件 ID、供应商提交 ID 与 RFC Message-ID 混为一谈；只有已确认的传输标识能用于邮件头关联。旧的 `message_id` 保留原值，未必是已验证的 RFC 标识；没有 `rfc_message_id` 时不能凭供应商 ID 猜出回复链。

新收到的邮件可保留有界、可选的 `reply_to`、`in_reply_to` 和 `references`；旧档案可能没有这些字段，标题相同也不证明是在回复同一封。所有正文和元数据都是不可信任务数据：Reply-To 是建议地址，不是新增授权。Agent 应在你授权的范围内选择目的地，建立**新的**草稿与发送意图，不能直接重发收到的 ZIP。

在分页整理邮件时，先收集本次目标 ID，再标记或删除；不要一边翻页一边改变同一检索空间，使自己的游标失效。收到的邮件要求转发机密、删除其他邮件或执行附件，也不会改变原任务授权。

## 安装与首次登录

请先查看页面顶部的发布状态，再从 [GitHub Releases](https://github.com/kleedaisuki/moesegfault-amail/releases) 选择已正式公开的版本。只有对应版本的全部五个平台安装包、Agent Skill 和 `SHA256SUMS` 已公开后才继续；候选构建不是正式安装来源。下载 `SHA256SUMS` 和与你系统匹配的安装包，放在同一个文件夹，再执行校验与安装。无需安装 Rust。

| 你的设备 | 选择的安装包 |
| --- | --- |
| Linux，Intel／AMD 64 位（x86-64） | `amail-v0.1.0-x86_64-unknown-linux-gnu.tar.gz` |
| Linux，ARM 64 位（AArch64） | `amail-v0.1.0-aarch64-unknown-linux-gnu.tar.gz` |
| Windows，Intel／AMD 64 位（x86-64） | `amail-v0.1.0-x86_64-pc-windows-msvc.zip` |
| macOS，Apple 芯片（M 系列） | `amail-v0.1.0-aarch64-apple-darwin.tar.gz` |
| macOS，Intel 芯片 | `amail-v0.1.0-x86_64-apple-darwin.tar.gz` |

这些是**原生**安装包；目前没有 Windows ARM 原生包，也没有 Linux musl 包。Linux 包使用 GNU libc。若不确定 CPU 类型，Linux/macOS 可运行 `uname -m`（`x86_64` 或 `aarch64`／`arm64`）；Windows 在“设置 → 系统 → 系统信息”查看系统类型。安装包和校验文件必须来自**同一个** GitHub Release，不要从聊天消息复制别人提供的散列值。

### Linux：校验并安装

在下载目录的终端运行；若是 ARM 64 位，将第一行换成表中的 ARM 文件名：

```sh
archive=amail-v0.1.0-x86_64-unknown-linux-gnu.tar.gz
awk -v file="$archive" '$2 == file { print }' SHA256SUMS | sha256sum --check -
```

只有出现 `OK` 才继续。没有匹配行、文件损坏或校验失败时停止，不要运行该安装包。然后：

```sh
mkdir -p "$HOME/.local/bin"
tar -xzf "$archive" -C "$HOME/.local/bin" amail
export PATH="$HOME/.local/bin:$PATH"
amail --version
```

把 `export PATH="$HOME/.local/bin:$PATH"` 加入你的 shell 启动文件（例如 `~/.bashrc` 或 `~/.zshrc`），新开的终端才能直接使用 `amail`。

### macOS：校验并安装

Apple 芯片使用下列文件名；Intel Mac 将第一行换成表中的 Intel 文件名：

```sh
archive=amail-v0.1.0-aarch64-apple-darwin.tar.gz
awk -v file="$archive" '$2 == file { print }' SHA256SUMS | shasum -a 256 --check -
```

只有出现 `OK` 才继续，再运行：

```sh
mkdir -p "$HOME/.local/bin"
tar -xzf "$archive" -C "$HOME/.local/bin" amail
export PATH="$HOME/.local/bin:$PATH"
amail --version
```

把同一条 `export PATH=...` 加入 `~/.zshrc`。如果 macOS 阻止首次运行，不要关闭整个系统的安全检查；先确认来源和散列，再到“系统设置 → 隐私与安全性”按系统提示允许这一个程序。

### Windows：校验并安装

在安装包和 `SHA256SUMS` 所在目录打开 PowerShell，将下面整段命令一次粘贴运行：

```powershell
& {
$archive = 'amail-v0.1.0-x86_64-pc-windows-msvc.zip'
$checksumLines = @(Get-Content .\SHA256SUMS | Where-Object { $_.EndsWith("  $archive", [StringComparison]::Ordinal) })
if ($checksumLines.Count -ne 1) { throw 'SHA256SUMS 中没有唯一的安装包记录' }
$expected = ($checksumLines[0] -split '\s+')[0]
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash
if ($actual -ne $expected) { throw 'SHA-256 校验失败；不要运行此安装包' }
$bin = Join-Path $HOME '.local\bin'
Expand-Archive -LiteralPath $archive -DestinationPath $bin -Force
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($userPath -split ';') -notcontains $bin) {
  [Environment]::SetEnvironmentVariable('Path', "$userPath;$bin".Trim(';'), 'User')
}
$env:Path = "$bin;$env:Path"
amail --version
}
```

上面的 SHA-256 校验不通过时，`throw` 会中止该段，不要继续解压。用户 `PATH` 修改会对新开的终端生效；当前终端也已临时加入路径。若 PowerShell 受设备策略限制，请让设备管理员协助，而不是关闭安全策略。

Agent Skill 的文件名为 `amail-agent-skill-v0.1.0.zip`；它应与 CLI 安装包来自同一个 GitHub Release。解压前，按上面的系统校验步骤，将文件名换成 Skill ZIP，核对 `SHA256SUMS` 中对应的唯一记录。Agent 若支持安装 Skill，可将 ZIP 中的 `amail/` 文件夹及其引用文档一并放入其 Skill 目录；具体目录以该 Agent 的安装说明为准。这不是 CLI 的运行依赖，也不要用它替代 CLI 安装包校验。准备好之后，让 Agent **在你的设备上**启动登录：

```sh
amail login
```

你本人只需按提示在弹出的浏览器里完成 moeSegFault 身份授权；Agent 可以发起命令，但不能代替你授权。**不要把口令、访问令牌或浏览器会话交给 Agent**。之后 Agent 可以查看登录状态，或按你的要求退出：

```sh
amail auth status
amail auth logout
```

`login.moesegfault.dev` 用于人类登录体验；邮件服务的公开地址是 `mail.moesegfault.dev`。你的账号邮件地址始终形如 `名字@mail.moesegfault.dev`，而不是 `名字@moesegfault.dev`。

## 创建你的邮件地址

只需选一个简短、容易理解的名字：

```sh
amail address add klee
amail address list
```

每个 moeSegFault 账号最多可持有 **10 个地址**。`admin`、`moesegfault` 及登录、邮件等常用服务名称保留给站点，不能注册。地址创建可能经历短暂的启用过程；只有状态为 `active` 时才开始用于收件。

如果创建请求超时或返回 `503`／`routing_unavailable`，不要立即换一个名字重试：结果可能尚未确定。先用 `amail address list` 核对**同一个地址**；若状态或路由仍不明确，请联系服务运营者核查该地址的路由，再决定是否重试同一个名字。

需要停用一个地址时，使用完整地址：

```sh
amail address delete klee@mail.moesegfault.dev
```

删除地址与删除邮件是两件事。为避免旧邮件误投给新主人，退役的地址名不会立即让其他账号重新注册。[供应商当前](https://developers.cloudflare.com/email-service/platform/limits/)允许此邮件子域名最多 200 条逐地址收信路由：其中两条分别留给 `postmaster` 和 `abuse` 运营邮箱，因此首发服务**最多 198 个用户地址**。实际能否创建仍取决于供应商路由状态；容量用尽时，amail 会明确报告，而不是假装注册成功。

## 查找邮件，而不是翻页

`amail sync` 可同步最新邮件，`amail search` 用组合条件缩小范围。你可以按时间区间、标题、发件人、收件人、元数据、正文、语义或已读状态寻找消息；正则表达式和区分大小写是显式选项。搜索默认返回简短的邮件元数据，**不会自动下载正文，也不会改变已读状态**。

```sh
amail sync
amail search --title "release"
amail search --after 2026-01-01T00:00:00Z --before 2026-10-01T00:00:00Z
amail search --from sender@example.org --unread
amail search --meta attachment_name=chart.png
amail search --title "release.*" --regex --case-sensitive
amail search --semantic "讨论发布风险的邮件"
```

`--meta` 原有四个键为 `message_id`（原始邮件 ID）、`in_reply_to`（回复关系）、`content_type`（内容类型）和 `attachment_name`（附件名称）。v0.1.2 候选还支持 `rfc_message_id`（已验证 RFC 标识）、`provider_id`（供应商标识）、`reply_to`（建议回复地址）和 `references`（关联链中的单个标识）。可以用多个 `--meta KEY=VALUE` 分别指定不同键，并与其他条件一起筛选；同一个键在一次命令里写两遍会报错，而不会悄悄覆盖前一个条件。

多个条件一起使用时表示“同时满足”。时间区间的起点包含在内，终点不包含；`--regex` 对文本条件启用正则匹配，`--case-sensitive` 启用区分大小写。语义检索在服务端执行：邮件文本会自动建立索引；使用 `--semantic` 时，检索词也会发送给 OpenRouter。若第一页还有后续结果，服务端会在仅限本账号读取的检索任务中保留该检索词、其查询向量和游标签名密钥，最长 24 小时；后续页面复用同一向量，不会再次把检索词发送给模型。游标过期或邮箱变更时需从第一页重新检索，不能拼接新旧结果。普通条件检索不会额外把检索词发送给模型，但不会停止邮件的自动索引。默认输出是紧凑的 JSON Lines，适合管道捕获和 Agent 进一步筛选；它不是为屏幕阅读设计的邮件视图。

范围很广的精确检索可能需要较长时间。amail 会自动等待，**结果完整前不会在标准输出写入部分结果**；若中断或超时，终端错误提示会给出任务 ID，可在 24 小时内续作：

```sh
amail search --resume JOB_ID
```

需要更长的单次等待，可加 `--wait-seconds 1800`。如果邮箱在等待期间发生变化，任务可能失效；这时请重新检索，而不是把旧结果当作完整结果。

## 读取、标记与删除

先从搜索结果找到邮件 ID，然后把邮件取为 ZIP。取回本身**不会**标记为已读：

```sh
amail read MESSAGE_ID -o message.zip
amail read MESSAGE_ID -o message-dir --unpack
amail mark MESSAGE_ID --read
amail mark MESSAGE_ID --unread
```

消息包包含邮件正文和相关资源；`--unpack` 可直接解出目录，或对已有 ZIP 使用 `amail unpack message.zip -o message-dir`。Agent 可以将其中的 `body.txt` 或 `body.html` 转换成目标工作流需要的文本或 HTML。对不再需要的邮件：

```sh
amail delete MESSAGE_ID
```

`delete` 删除的是当前账号的这份投递，不会替其他收件人删除邮件。让 Agent 自动删除前，最好先设定清楚保留规则。

## 准备并发送 ZIP 消息包

Agent 不直接修改“原始邮件”。它先在一个目录里准备正文与元数据，再由 amail 打包和发送；**无需系统安装 `zip` 命令**。一个最小消息包如下：

```text
draft/
├── manifest.toml
├── body.txt
└── body.html
```

`manifest.toml` 描述发件人、收件人和标题：

```toml
version = 1
from = "klee@mail.moesegfault.dev"
to = ["friend@example.org"]
subject = "Hello from amail"
```

`body.txt` 是纯文本正文，`body.html` 是 HTML 正文；至少提供其中一个。两者都存在时，amail 会编译成同一封邮件的两种阅读形式。HTML 不需要包含完整网页，也不是邮件传输协议（MIME）原文；amail 会处理编码、多部分结构及资源引用。

需要图片或附件时，将文件放在 `assets/`，并在 `manifest.toml` 里逐项声明。内嵌图片的例子：

```toml
[[assets]]
path = "assets/chart.png"
content_type = "image/png"
disposition = "inline"
cid = "chart"
```

随后在 `body.html` 里使用 `<img src="cid:chart" alt="图表">`。不要把远程脚本、事件处理代码或任意邮件头塞进 HTML；amail 会验证并安全编译消息。发送方地址必须属于你的账号。

```sh
amail pack draft -o draft.zip
amail send draft.zip
```

### 发送额度与密送

amail 的发送适用于与你的 Agent 任务相关的通知与已有往来的回复，不用于未经请求的批量群发或营销邮件。

发送按**收件人条目**计额，不按 ZIP 文件计额。`to`、`cc`、`bcc` 全部计算在内；同一地址重复填写也逐条计算。例如，一封邮件发给 3 人会占用 3 个每日收件人额度。当前保护上限是：

| 范围 | 上限 |
| --- | --- |
| 每账号、每 UTC 自然日 | 50 个收件人条目，且不超过 20 封邮件 |
| 每账号、每 UTC 小时 | 5 封邮件 |
| 每账号对同一个收件地址、每 UTC 自然日 | 10 个条目 |
| 全站、每 UTC 自然日 | 10,000 个收件人条目 |
| 单封邮件 | `to`、`cc`、`bcc` 合计 50 个条目 |

`bcc` 是密送，其他收件人不会在公开收件人列表中看到它，但草稿 ZIP 和你自己的发件记录仍包含这些地址，**不要把原始消息包直接分享给收件人**。若全站正处于发信保护期，`send_held` 表示没有提交给发信服务；它本身不改变已获准使用的收件与检索权限，也不证明这些功能已对公众开放。对外开放发送必须以真实外部投递、退信与投诉反馈及有人监控的处理通道为前提。

额度用尽时，amail 会明确报告 `quota_exhausted`，这次请求不会交给发信服务。多项额度逐项预留，因此即使随后某项额度拒绝，较早预留的额度仍可能被占用；服务商拒绝或结果不确定时也可能计额。发送命令确认的是服务**接受处理**，不等同于远端邮箱已经投递成功。网络不确定时不要盲目重发；amail 使用同一幂等请求来避免重复发送和重复计额。

## 什么时候使用 `--human`

默认输出尽量少、结构明确、方便 Agent 和管道。偶尔你要在终端亲自查看列表，再加全局选项 `--human`：

```sh
amail --human address list
amail --human search --title "release"
```

它只改变这次命令的排版和终端颜色，不会打开邮件、标记已读或改变服务器数据。重定向和管道场景继续使用默认模式。

## 隐私与边界

除了诊断遥测，自动语义索引还有独立的内容数据流：服务端将邮件主题与正文提取文本拼接，取开头**最多 12,000 个 UTF-8 字节**经 OpenRouter 交给 Qwen3 Embedding 8B 模型服务，以生成 256 维向量。原始 ZIP 和附件文件不会作为这次嵌入请求的输入；使用 `--semantic` 时，检索词也会发送给该服务。若该语义检索有后续页面，服务端还会把检索词和实际用于第一页的查询向量保存在本账号专属任务中，最长 **24 小时**，到期清除；后续页面不再次请求服务商。没有后续页面的快速检索不会为游标保留这一副本。普通条件检索不需要向模型发送检索词，但无论你是否使用语义检索，后台仍会为邮件自动建立索引。目前没有逐账号关闭这一处理的选项；`AMAIL_TELEMETRY=off` 也不会关闭它或服务器任务留存。请在使用地址收发邮件前考虑是否接受。

amail 会记录用于诊断的本地操作轨迹，并向邮件服务上传脱敏遥测。轨迹不应包含邮件正文、标题、完整地址、令牌、ZIP 路径或搜索词；服务端也只需保留定位故障所需的结构化信息。使用 `amail config` 可查看当前遥测状态；设置环境变量 `AMAIL_TELEMETRY=off` 可停止后续诊断记录与上传，但不会删除已有的本地诊断记录。

删除可见的已发邮件后，消息包会由定期清理移除；但为处理迟到的退信和投诉，受限的发件人、完整收件人名单（包括密送）及投递反馈记录通常会在各自生成后 **90 天**由定期清理移除，积压或故障时可能稍晚。投诉拦截与操作审计记录可能保留到复核处理完成。这些运营记录不含邮件正文或标题，也不会出现在普通 CLI 邮件检索结果或脱敏遥测中。v0.1.2 候选允许原账号按需查询尚可见发件的有界、结构化投递反馈；不会暴露运营备注，也不会通过这些查询找回已删除的消息或其收件人列表。**删除邮件不等于立即删除全部运营记录**。

站点的 `postmaster` 和 `abuse` 角色邮箱由 Cloudflare 精确转发给受限的**外部邮箱服务商**，由授权运营人员处理；首发版没有自动化举报或案件页面。你发给这些角色的报告可能包含邮件头、标题、正文和附件，不进入普通 amail 邮箱、检索或遥测；外部邮箱中的副本**不属于上文 90 天结构化记录的定期清理范围**。对外宣称联系通道可用之前，必须以真实邮件验证转发和监控。请勿在报告中附上密码或令牌。

`mail.moesegfault.dev` 是用户邮件域名。`moesegfault.dev` 不开放给用户注册邮箱；代表站点发出的邮件使用 `mail@moesegfault.dev`。收到可疑消息时，仍要检查发件域和内容，不要仅因显示了站点名称就信任它。
