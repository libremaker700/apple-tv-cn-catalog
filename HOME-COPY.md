# 首页轮播中文文案

`scripts/home_copy.py` 只处理美国官网首页作品轮播的短介绍、更新提示和榜单提示，不修改国内片名、别名、分季或片源绑定。专题没有该字段时，App 继续使用原来的简介。

- 定时入口仍为 `update.yml` 的每 6 小时采集。首页采集成功后，用同一份官网 HTML 获取文案，再发布完整快照。
- push 或手动选择 publish 时，只补充文案，不重新采集图片与全部作品。
- Repository Secret 为 `GEMINI_API_KEY`；可选 Repository Variable `HOME_COPY_MODEL` 固定型号。默认从模型列表选择支持 generateContent 的型号，404 时最多尝试 3 个。不会为翻译开启联网搜索。
- 依赖沿用 requests、Pillow、opencc-python-reimplemented。运行 `python scripts/home_copy.py`；校验 `python scripts/home_sync.py --validate`；测试 `python -m unittest discover -s tests -v`。
- 缓存键包含脚本翻译版本、官方作品 ID 和英文短介绍。顺序、榜单或更新时间变化不会重复翻译同一句介绍。失败退避 6 小时，原文变化时不使用旧原文的译文。
- `data/home-copy-cache.json` 保存译文；`logs/home-copy.json` 保存本轮缓存命中、调用数、HTTP 状态、模型和 usage。密钥只通过 Actions 环境变量传入，不写入数据或 APK。
- 榜单名次、更新星期与年份按官网原文确定性转换；未识别的提示保留英文来源但不显示未经翻译的提示，不让模型编造排名。
- `data/home-copy-reviewed.json` 可记录人工核对的改译，只有官方 ID 和英文原文完全相同才使用；换文案自动失效。公开字段 translationMethod 区分 machine、reviewed、pending。
- 译文文件先按 SHA-256 写入 releases，再更新 version.json。图片库存不变，App 更新文字时复用已有图片。失败时保留上次有效快照或已有中文简介。

当前范围是首页的 9 个作品轮播，不包含订阅广告、价格、试用按钮，也不把作品名的直译当作国内片源搜索名。海报艺术字仍使用官方图片。
