---
layout: ../layouts/ManualLayout.astro
title: 用户手册
description: amail 的安装、登录、地址管理、邮件检索和 ZIP 收发指南。
---

## 先认识 amail

amail 是一个面向 AI Agent 的命令行邮件客户端。你在浏览器里完成 moeSegFault 登录；此后 Agent 可以通过 amail 注册地址、检索邮件、更新状态和发送消息。它**没有收件箱网页，也没有 `view` 命令**：邮件内容以 ZIP 消息包交接，默认检索输出则是适合继续处理的紧凑数据。

| 你负责 | Agent 可以负责 |
| --- | --- |
| 明确完成登录授权 | 注册与管理邮箱地址 |
| 决定哪些任务交给 Agent | 同步、检索、读取、标记、删除邮件 |
| 检查重要对外沟通 | 准备 ZIP 并调用 amail 发送 |

## 安装与首次登录

从 [GitHub Releases 下载 v0.1.0](https://github.com/kleedaisuki/moesegfault-amail/releases/tag/v0.1.0) 中适合你系统的 amail，放到 `PATH` 中。支持 Linux、macOS 和 Windows。若你使用 Agent，也可下载同一版本的 [Agent Skill](https://github.com/kleedaisuki/moesegfault-amail/releases/download/v0.1.0/amail-agent-skill-v0.1.0.zip)。然后由你本人执行：

```sh
amail auth login
```

按提示在浏览器完成 moeSegFault 身份授权。登录是需要人参与的步骤；**不要把口令、访问令牌或浏览器会话交给 Agent**。你可以随时查看登录状态，或退出：

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

多个条件一起使用时表示“同时满足”。时间区间的起点包含在内，终点不包含；`--regex` 对文本条件启用正则匹配，`--case-sensitive` 启用区分大小写。语义检索在服务端执行，会把检索词和待索引的邮件文本发送给 OpenRouter 的嵌入服务；如果不愿意让这些内容经过第三方模型提供者，请不要使用语义检索。普通检索可独立使用。默认输出是紧凑的 JSON Lines，适合管道捕获和 Agent 进一步筛选；它不是为屏幕阅读设计的邮件视图。

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

`bcc` 是密送，其他收件人不会在公开收件人列表中看到它，但草稿 ZIP 和你自己的发件记录仍包含这些地址，**不要把原始消息包直接分享给收件人**。若全站正处于发信保护期，`send_held` 表示没有提交给发信服务；收件与检索仍可使用。首次开放发送前，站点会先验证真实外部投递及退信、投诉反馈链路。

额度用尽时，amail 会明确报告 `quota_exhausted`，这次请求不会交给发信服务。多项额度逐项预留，因此即使随后某项额度拒绝，较早预留的额度仍可能被占用；服务商拒绝或结果不确定时也可能计额。发送命令确认的是服务**接受处理**，不等同于远端邮箱已经投递成功。网络不确定时不要盲目重发；amail 使用同一幂等请求来避免重复发送和重复计额。

## 什么时候使用 `--human`

默认输出尽量少、结构明确、方便 Agent 和管道。偶尔你要在终端亲自查看列表，再加全局选项 `--human`：

```sh
amail --human address list
amail --human search --title "release"
```

它只改变这次命令的排版和终端颜色，不会打开邮件、标记已读或改变服务器数据。重定向和管道场景继续使用默认模式。

## 隐私与边界

amail 会记录用于诊断的本地操作轨迹，并向邮件服务上传脱敏遥测。轨迹不应包含邮件正文、标题、完整地址、令牌、ZIP 路径或搜索词；服务端也只需保留定位故障所需的结构化信息。使用 `amail config` 可查看当前遥测状态；设置环境变量 `AMAIL_TELEMETRY=off` 可停止后续诊断记录与上传，但不会删除已有的本地诊断记录。

删除可见的已发邮件后，消息包会由定期清理移除；但为处理迟到的退信和投诉，受限的发件人、完整收件人名单（包括密送）及投递反馈记录通常会在各自生成后 **90 天**由定期清理移除，积压或故障时可能稍晚。投诉拦截与操作审计记录可能保留到复核处理完成。这些运营记录不含邮件正文或标题，也不会出现在 CLI 检索结果或脱敏遥测中；**删除邮件不等于立即删除全部运营记录**。

`mail.moesegfault.dev` 是用户邮件域名。`moesegfault.dev` 不开放给用户注册邮箱；代表站点发出的邮件使用 `mail@moesegfault.dev`。收到可疑消息时，仍要检查发件域和内容，不要仅因显示了站点名称就信任它。
