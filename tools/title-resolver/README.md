# Apple TV 国内片名与简介核验

此流程只整理资料和名称，不下载影片。App 收到核验后的中文名及别名，继续通过原有 15 个站点按作品类型、年份、季数匹配；找到线路、返回集数、实际可播放是三种不同的验收结果。

## 顺序

1. 复用身份一致的已核验资料。已有有效中文简介不会被覆盖。
2. 豆瓣 suggest 用 Referer 与 X-Requested-With；条目走移动端 JSON。电视剧固定 `/tv/`，电影固定 `/movie/`，忽略 suggest 常见的错误 type。
3. 核对英文原名、类型、首播年份，拒绝错片和第二季冒充第一季。延期年份变动只在已知 IMDb ID 精确相同时接受。
4. 豆瓣无结果时查中文维基，要求正文身份与明确的中国大陆名称字段，不把繁体标题直接当大陆译名。
5. 仍有缺项时，一批最多 5 部作品只发一次 MiniMax 查询。模型只提供候选名称及链接；脚本自己重新请求豆瓣、维基或百度百科核验，不采信模型的正文、ID、评分或自译简介。
6. 最后使用已有 Tavily 搜索预算，额度保留在原 `data/title-cache.json` 中，默认每月上限 100；不会换 Key 绕过额度。MiniMax 每月最多 20 批，在发送前落账。
7. 只有通过核验的名称、别名、简介进入片库。资料与真实图片先准备好，最后发布版本清单。App 下载新版本；网络失败保留本地有效版本。

豆瓣 HTTP 200 空数组、访问限制或接口错误，均为待重试，不能据此判定作品未收录。401/429 不连续重试。豆瓣请求跨两个域名共享至少 1.8 秒间隔，已有公共源主机冷却机制保留。默认失败次日再查；单部作品可人工 `--force`。

## 用法

依赖 Python 3.12+、requests、Pillow、opencc-python-reimplemented。可选 MiniMax 还需要 Java 17 JDK；设置 JAVA_HOME，首次使用从 Maven Central 下载固定版本 JSON jar，并校验 SHA-256。

```powershell
.\tools\title-resolver\run.ps1 -Titles 'Being Heumann','Nocturne' -Limit 2 -AsJson
.\tools\title-resolver\run.ps1 -Slugs 'neuromancer' -Limit 1 -Force -AsJson `
    -CredentialsPath 'C:\Users\muyi\Desktop\PrimeVideo\.local\minimax-credentials.json'
```

此入口只处理 Apple 片库已存在的作品，以官方 slug 为稳定键；通用英文标题查询继续用 Prime 原 `tools/prime-official/douban-title-lookup.ps1`。Prime 的脚本和 Java 原文件均未改动。vendor 中的 Java 客户端是原文件的逐字副本，只调用其签名函数；SignBridge 补齐 GET 的 `{}` 参与 yy 签名、查询参数加号编码和流式 token 参数。

Linux / GitHub：

```sh
python scripts/resolve_titles.py --slug being-heumann --limit 1 --force
python -m unittest discover -s tests -v
python scripts/catalog.py --validate
```

`--no-publish` 不切换 App 清单，但会保存核验缓存、报告及导出表。正式发布仍须独立校验通过。

## 输出

- `docs/title-map.json`、`docs/title-map.csv`：英文名、中文名、豆瓣链接/ID、类型、年份、可核实的评分/评价人数、置信度和来源。未核实项显式保留；App 的英文回退名不会被改成“未收录”。
- `logs/title-resolver.json`：各步骤、公开源 HTTP 状态、AI usage、预算保留、发布变更。不会存模型完整对话、思考过程或登录凭证。
- `data/title-cache.json`：复用原身份缓存；`data/agent-title-cache.json`：批次额度和重试队列。
- `VERIFIED` 表示名称身份通过；`NO_RATING` 表示名称通过但没有有效豆瓣评分。`DISPUTED`、`POSSIBLE_FALSE_POSITIVE`、`UNVERIFIED` 均不更新片名。`provider_status=NATIVE_CHECK_ON_OPEN` 不代表已播放成功。

## GitHub 与登录

现有 title-update 工作流每天 03:47 UTC（北京时间 11:47）执行，默认每批 3 部，手动可限定 slug。Secrets 原有 Tavily 配置继续使用；可选新增 `MINIMAX_CREDENTIALS_JSON`，内容是有效的 `{ "base":"https://agent.minimax.io", "token":"...", "user_id":"真实 realUserID", "op_ticket":"..." }`。国内账户必须使用对应国内入口。

MiniMax Web 登录令牌会失效。当地登录文件自动续期不会同步改写 GitHub Secret；更新后需重新保存 Secret。无凭证或 401 时流程保留已有资料，记录降级结果，继续公开源和预算内的 Tavily 核验。不能把工作流成功视为 MiniMax 接口成功。当前是否跑通以本次报告的 agent.status 为准。

凭证始终留在本机私有文件或 GitHub Secrets，不进 APK、仓库、CSV 或公开日志。原 Prime 续期任务不在此项目修改范围。
