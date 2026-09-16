# P6 — QQ 通道

| 项 | 内容 |
| --- | --- |
| 阶段 | P6 |
| 首次版本 | v0.2 |
| 最近修订 | v0.11 |
| 变更记录 | [变更/](../变更/) |
| 依赖 | **执行顺序：** P5 已验收。**逻辑硬依赖：** P2-A（同一记忆）。P4 不是 QQ 文字的逻辑前提，但本仓库不并行开工 QQ 登录，争论时只看总纲 §3.1 |
| 下一阶段 | [P7-微信通道.md](./P7-微信通道.md) |
| 总纲 | [开发文档.md](./开发文档.md) |
| 原则 | [双模式说明.md](./双模式说明.md) |
| 本阶段目标 | QQ 里她是会自己决定说不说的群友：能发/收/生成表情包；不是桌宠那种不停找你聊。自主发言状态机本阶段一次性做完 |

---

## 1. 本阶段要做成什么样

QQ 事件进入同一套 Agent / 记忆，但**策略与桌宠相反**：

- 先看、再决定、可以不说
- 说话像群友：短、可以分条、可以只丢表情包
- 能收集群友表情包，能从本地库挑选发送，能用 MCP 生成新表情再发
- 进你自己的群：学习与发言分开

本机桌宠的「连续聊 + 主动找你 + 看屏幕」**已经在 P5 做完**，本阶段不要把看屏接到群里。

进入本阶段才选怎么连 QQ。**P6 之前**不得出现登录器。P6 之前允许的预研：读官方文档、写选型笔记、用群导出文本跑 P2-B 导入脚本。

### 1.1 要做

- `channels/qq.py`：收、发、白名单、限频
- **自主发言**：群消息默认入未读；Agent 可 `silent`；禁止条条自动回复
- 私聊你：比群积极，但仍允许短回、表情、偶尔不接（不要桌宠式主动刷屏）
- 表情包库：`data/stickers/` + 索引
- 收集群 U 表情包（去重、来源、可删）
- MCP（或同等 tool）：列/发/收/备注/生成表情包
- 文本进 P2 ingest（pending）
- 图片/普通图可后做识别；表情文件本身要能保存

### 1.2 明确不做

- 桌宠主动搭话、截屏 CV
- 微调模型
- 采集无管理权的群
- 把网页改成「QQ 专用大脑」

---

## 2. 通道与策略

```text
QQ 事件
  → QqChannel 译成 Inbound（含 sticker 附件）
  → policy/qq.py（未读队列、是否唤醒）
  → Agent（可调 MCP）
  → Outbound { silent, texts[], sticker_ids[], generated? }
  → 非 silent 才 send（文字 / 表情）
```

`chatId`：

- 私聊：`qq:private:<id>`
- 群：`qq:group:<id>`

profile 跨通道共享。QQ 策略**不得**调用本地看屏工具。

---

## 3. 接入方式（开工时拍板）

| 方式 | 体验 | 表情包 |
| --- | --- | --- |
| A. 官方 QQ 机器人 | 机器人号 | 多半只能发图片冒充表情；能力看开放平台 |
| B. 专用个人号 + 网关 | 普通好友 | 更接近真表情包收发；P6 再定网关 |

Core 只认：

```text
send_text(chatId, texts[])
send_sticker(chatId, file_path | sticker_id)
```

要「像群友发表情」就优先选表情能力完整的接入；凭证与记忆文件分离。

官方接口：[QQ 机器人](https://bot.q.qq.com/wiki/)。

---

## 4. 自主发言（P6 就必须有，不是摆设）

### 4.1 错误做法

群里每条消息 → 直接 `agent.run` → 把回复发出去。

### 4.2 正确做法（最低可用）

1. 消息先进入该 `chatId` 的未读缓冲（含谁、是否 @、是否表情、引用）
2. 唤醒条件（config）：被 @ / 点名 / 关键词 / 私聊 / 缓冲条数或等待超时
3. Agent 一次看到**一批**未读，而不是一条逼一次回复
4. 输出必须能 `silent: true` → 通道发 0 条
5. 也可以：只发表情、只回一句、回多句、先收表情再潜水

推荐让模型走工具（MCP），而不是通道替她决定「这次该回」：

- 想说话：`qq_send_text` / `qq_send_sticker`
- 不想说话：不调用发送工具（或显式 silent）
- 想等：`qq_wait`（P6 可先用超时唤醒代替）

P6 第一版允许「规则唤醒 + 模型 silent」。观望/活跃状态机也在本阶段做完第一版，**不要留到后面推翻协议**。`silent` 只来自 `[[atri]]` 尾块（或工具未调用发送），解析失败时按总纲降级为 `silent=false` 前，QQ 策略仍可选择不 `send`（通道限频与白名单优先于模型胡言）。

### 4.3 配置

```yaml
channels:
  qq:
    enabled: true
    allow_private: []
    allow_groups: []
    deny_private: []
    deny_groups: []
    allow_all_when_empty: false
    send_delay_ms_min: 800
    send_delay_ms_max: 2500
    max_chars_per_msg: 500
    policy:
      mode: autonomous          # 禁止 auto_reply_all
      private_more_responsive: true
      group_default_silent: true
      wake_on_at: true
      wake_on_name: true
      wake_keywords: []
      batch_window_ms: 8000
    learn_groups: true
    stickers:
      dir: data/stickers
      auto_collect_group: true    # 仍建议 Agent 决定收不收；也可规则先收下再待整理
      generate_max_per_hour: 4
```

白名单 fail-closed，与总纲一致。

---

## 5. 表情包

### 5.1 本地库

```text
data/stickers/
  index.json          # 或 sqlite 表 stickers
  files/<hash>.png|gif|webp
```

索引字段：`id, hash, path, tags[], source_group, source_sender, note, created_at, last_used_at`

管理页 `/stickers`：预览、改标签、删除。未进 git。

### 5.2 收集群 U 表情

- Inbound 识别 `rawType=sticker`（以及当成表情发的短图）
- 工具 `qq_collect_sticker`：存文件、写来源、hash 去重
- 可选：群内表情自动先入库为 `unreviewed`，你在管理页确认后 Agent 才能拿去发（防脏、防隐私图）
- 只对 `allow_groups` 生效

### 5.3 发送

- Agent 选 `sticker_id` 或刚生成的 path
- Channel `send_sticker`
- 可以「表情 + 一句话」，也可以「只发表情」
- 发表情也算发言，要走限频

### 5.4 MCP 生成

工具 `sticker_generate`：

1. 入参：`prompt`（画面）、可选 `caption`（表情上的字）
2. 调你配置的生图后端（云端 API 或本地），密钥只在 tool 进程
3. 落盘入库，打标签 `generated`
4. 返回 `sticker_id`，由模型再调 `qq_send_sticker`

约束：

- 每小时上限、单日上限
- 生成失败 → 改用已有表情或文字
- 不做违法违规内容；prompt 可加一条固定安全前缀
- 生图延迟高：先可在群里不发「正在画」，避免连发状态刷屏（config）

---

## 6. MCP 工具清单（安全子集）

`src/mcp/qq_social.py`（DSH/自建 Agent 都能调同一套）：

| 工具 | 白名单 |
| --- | --- |
| `qq_get_unread` / `qq_get_recent` | 只读允许的会话 |
| `qq_send_text` | 发送对象必须 allow |
| `qq_send_sticker` | 同上 |
| `qq_list_stickers` | 只读本地库 |
| `qq_collect_sticker` | 只允许的群 |
| `qq_sticker_note` | 改备注 |
| `sticker_generate` | 限频；不直接发到群，只入库 |

禁止：任意好友轰炸、CQ 码注入、发文件到非白名单。

群聊 system 附加：

- 你是群友不是客服
- 可以只用表情包回答
- 没意思就别说话
- 不要解释你在用工具

---

## 7. 群学习（仍不微调）

与 P2 ingest 共用。发言与学习分开：silent 的消息照样可以进 pending 黑话/关系。

---

## 8. 实现顺序

1. 选定 A/B，白名单私聊 ping/pong
2. 私聊经 Agent；确认可 silent（测试提示「这句别回」）
3. 群：未读批量 + 默认不回 + @ 才回
4. 表情库 + 发送已有表情
5. 收集群表情 + 管理页
6. `sticker_generate` MCP + 发出去
7. ingest 学习队列
8. 验收

---

## 9. 验收

- [ ] 私聊人设、记忆与网页一致
- [ ] 群里普通闲聊大部分 **不回**
- [ ] @ 或点名会回；可以只发表情包
- [ ] Agent 输出 silent 时通道一条都不发
- [ ] 能从本地库发表情包
- [ ] 群友表情能入库，管理页能看见来源并删除
- [ ] MCP/工具能生成一张表情并实际发到白名单会话
- [ ] 生成达到小时上限后改走已有表情或文字，不崩
- [ ] 空白名单不能外发（含表情）
- [ ] 无截屏、无桌宠主动找你的逻辑

---

## 10. 交给 P7

- P7：个人微信文字通道；必须先做合规可行性确认；不要上企业微信 / 公众号
- 桌宠与 CV 已在 P5 完成；不要把 `see_screen` 接到 QQ
- P2-B 若尚未做完，群学习可以先只进 pending 事实，风格库随后补
