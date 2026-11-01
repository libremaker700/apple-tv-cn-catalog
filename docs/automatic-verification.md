# 自动核验与三天采集周期

自 2026-11-01 起，以该日为锚点，每隔三个自然日运行采集、名称核验和片源复核。GitHub 每天只执行轻量日期判断；不符合周期的日期跳过采集作业，避免 cron 按月重置造成间隔失真。北京时间分别为 08:37（官网目录/图片）、11:47（名称/资料）、14:17（片源）。GitHub 调度可能延迟，手动任务与代码发布不受日期限制。代码推送只验证与发布已有资料，不调用简介/轮播翻译。

名称队列按最后尝试时间轮转，已有中文名但缺豆瓣资料的作品同样处理。英文标题豆瓣条目通过原名、年份、类型及季数检查后，只保存身份，不宣称取得中文名。自动补查使用最多四个去重关键词；关键词来自已有候选、原名及 YDC/Tavily 搜索线索，不能独立批准名称。候选名流程禁止使用 Gemini；名称工作流也不接收 Gemini Secrets。

扩大查询覆盖已配置的 CMS 和专用适配，每个片库每轮最多三页、五次详情补充，四并发，每作品最多约九十秒扩大查询预算。候选必须通过有效编号或导演及主要演员等强身份依据，并保留季数、年份与类型限制。公开报告不包含播放 URL、片库记录 ID 或私有配置。翻页、详情中断的偏移按片库保存，下轮继续。通过后回写别名，再进入既有的片库数量投票；没有证据时自动保留待重试，不需要用户逐条复核。

搜索账户支持 YDC 与 Tavily 多账户。明确的余额/额度耗尽（包括账户返回的额度错误）停用该账户到本轮结束，并切换下一账户，随后可切换另一搜索服务。鉴权、限流及网络故障分别记录，不冒充余额耗尽；空结果不切换账户。Gemini 只用于独立的海报官方内容翻译。只使用 Actions Secrets，报告仅包含账户变量名与状态，不记录密钥或上游错误正文。应用的总请求预算仍然有效，所有搜索账户都不可用时保留缓存等待后续周期。

详情中文名、简介、评分仍来自同一个已核验豆瓣作品响应；没有中文标题的条目不能与 CMS 简介或评分拼成豆瓣详情包。顶部官方轮播翻译流程独立保留。API 返回媒体入口、清单/分片可访问和播放器出画面分别验证。

2026-11-02 correction: PR subseries pages can restart artwork folders at season-01 while the Apple show continues an existing series. `data/season-scopes.json` binds a reviewed PR entry to its exact official show/season ID, year and release date. Publication and collection reject changed identities; the original parent entry keeps earlier seasons. Prehistoric Planet: Ice Age is scoped to season 3 (2025), Douban 37457350, not the 2022 first season. A same-response Douban title/synopsis/score packet is retained without rating counts.

Source query policy v6 keeps exact names and adds bounded punctuation/whitespace-stripped variants before response identity checks. This is retrieval only: season, year, medium, commentary exclusions and conflicting IDs remain enforced. Up to 12 queries per provider remain subject to the existing provider/work deadlines and cancellation. Old negative source-cache results are invalidated by the new query policy.
