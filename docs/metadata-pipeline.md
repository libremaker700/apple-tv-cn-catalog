# 中文片名、详情简介与豆瓣评分同步

当前 GitHub 入口为 scripts/mainland_names.py（title-update.yml）。App 消费发布后的完整资料包，电视不保存搜索密钥，也不在打开影片后分别补查片名、简介、评分。旧的 title_lookup.py / resolve_titles.py 工具仍可用于已核验名称缓存，但不是当前定时任务入口。

## 一次作品响应，形成一个详情包

1. 按 Apple 官方作品身份、英文原名、类型、当前季数和该季年份检查缓存。已有中文名但缺少详情包的作品也进入队列，每次仍最多检查 5 部，默认 3 部。
2. 先通过豆瓣公开建议接口定位作品，再读取该豆瓣条目的完整 subject 响应。搜索建议、网页摘要、模型回答不能独立证明同片。最多 2 个去重查询，每查询最多读取 3 个候选条目；已有中文名可以作为第二个定位词，仍须核验英文原名。
3. 同一响应中的中文片名、intro、rating/value/count 一起生成 zh.detailMetadata。同时按季保存在 zh.detailSeasons 数组。简介缺失时 summary 为空且 summaryStatus=PENDING；没有实际有效分数/评分人数时 ratingStatus=NO_RATING 且省略 rating/ratingCount，不能使用片源分数代替。
4. 现有中文名的片库数量投票规则继续在 GitHub 运行。详情包保留豆瓣原始中文名和 subjectId 作为证据；投票产生的显示名不会改变这个包的作品/季身份。
5. 原子包保存到 data/detail-metadata-cache.json，与主目录、主页作品一起发布；内容文件和图片先完成，最后切换内容寻址 manifest。已有图片不重复生成。

## 包结构

`detailMetadata` 为单包兼容指针，`detailSeasons` 为完整包数组。消费者使用前必须比较季数，不能把单包指针视为整剧通用分数。

```json
{
  "schema": 1,
  "source": "douban",
  "subjectId": "36689816",
  "sourceUrl": "https://movie.douban.com/subject/36689816/",
  "season": 6,
  "year": 2026,
  "title": "流人",
  "summary": "已核验的豆瓣中文剧情简介，完整内容与其余字段来自同一条作品响应。",
  "summaryStatus": "AVAILABLE",
  "ratingStatus": "AVAILABLE",
  "rating": 7.2,
  "ratingCount": 18493,
  "checkedAt": "2026-11-01T00:00:00+00:00",
  "originalTitle": "Slow Horses"
}
```

上例仅展示字段结构，checkedAt 为示例时间，实际包使用实际检查时间。电影 season=0，剧集 season=1..100；year 为整数；checkedAt 是带时区的 ISO8601 字符串。中文简介最多 600 字，AVAILABLE 至少 35 字且含 20 个汉字；评分必须为有限数且 0<rating<=10，ratingCount 为正整数。

## 身份与分季边界

- 英文原名、类型、年份必须对应；延迟年份只允许独立已知 IMDb ID 完全相同的例外。
- 未标季数的电视条目仅视为第一季，后续季必须有明确季数；中文标题与 original_title 的季数冲突直接拒绝。
- 不同季不能使用同一豆瓣 subjectId。第六季只能显示第六季包，不能沿用第一季或整剧的评分。
- 旧缓存只迁移此前独立核验过的豆瓣响应字段；不把旧 Gemini 简介、CMS 评分和另一个条目的名称拼成包。
- 缓存已完成包复用 7 天；缺简介或失败结果按既有 1 天重试时间排队。403/418/验证和网络故障保持 PublicPages 主机暂停机制，429 暂停 24 小时；不绕过验证或切换密钥规避限流。
- 未发布作品仍只处理资料，发布前不查播放源。

## 轮播文案

顶部轮播 copy.descriptionZh 等文案继续由 home_copy.py 使用 Gemini 翻译官网原文。旧 zh.summary 兼容官方译文也保留；它不能覆盖独立 detailMetadata / detailSeasons。App 详情页优先按当前季读取原子包，缺包不冒充已完成豆瓣资料。

## 2026-11-01 实际覆盖

本次共发布 4 个通过身份核验的豆瓣详情包：Nocturne 第1季、Prodigies 第1季、Long Way Round 第1季、Slow Horses 第6季。前三个中有 3 个旧响应可安全迁移；流人第6季重新定向请求验证。流人英文分季查询返回空，已有中文名查询找到条目后，实际 subject 的英文原名、2026 年、电视剧类型和第6季均匹配；返回分数为 7.2、评分人数 18493。旧截图中的 9.4 未被视为第6季评分。

Nocturne 和 Prodigies 实际没有有效评分，均发布 NO_RATING。Long Way Round 返回 9.2 / 1782 人。评分是本次数据快照，不是永久数值。

其余作品继续按上限逐作品补全，不宣称 326 部目录已全部获得豆瓣资料。这里的“同时获取”指同一作品的字段随同一个条目响应与发布包交付，不是无上限并发抓取整个片库。