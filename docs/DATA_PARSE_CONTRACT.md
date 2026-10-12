# 数据解析合同 steam-parse/v1

2026-10-11用户明确采用B05保守推荐；授权见[决议D-024](DECISIONS.md)。本合同已定版，机器政策源为[config.py](../config.py)的data_policy_contract().parse；配置版本v1.2，业务基底v1.1不变。[解析实现](../src/steam_parse.py)已接入独立的v1.2路径；53条P05的实际执行证据见[实现记录](DATA_CONTRACT_IMPLEMENTATION.md)。正式文件验收与独立消费者核验已完成，当前交接见[正式验收](DATA_HANDOFF_ACCEPTANCE.md)及[建模指南](MODELING_HANDOFF.md)。

## 字面输入、键及原值

读原始CSV时一律字面字符串，先保留原值，再分类空串/纯空白/声明缺失，再依字段转换。不依赖pandas默认NA词表，不经float中转解析整数，不静默删行/补值/裁剪。1-based source_row_no指CSV数据记录号，不是含换行时的物理行号。

合同不另设128 KiB字段长度限制。原始CSV与交接CSV的读取共用`csv_field_limit()`：在完整读取期间临时提升至平台可支持的宽字段上限，结束或失败时恢复调用前设置；项目内读取用同一锁串行保护该进程级设置。长前导零仍按既有十进制量级检查，不能因CSV默认上限或解释器`int()`字符上限而拒绝已合法的字面键。

appid：strip后全匹配ASCII [0-9]+，精确量级在0..9223372036854775807；保留前导零，键类型字符串。全序为ASCII字面序，不按浮点/数值排序。appid_raw与appid_parsed是提案名称，正式交付统一为raw_appid与appid。逐表报告raw与strip双基数、重复与碰撞，不能相加；主表和每辅助表各自唯一，跨表相同键用于join。steamspy_tag_data.csv源键appid，其他四张辅助表源键steam_appid，各映射到同一规范appid。不同原文strip成同一键或本来重复均阻断，不择优/合并/去零。空/白与非空非法分别诊断，但坏键整包阻断，包括辅助表；原记录仍以source_file/source_row_no对账。

## 缺失、标量与非法值

缺失词只用当前ENTITY_MISSING_TOKENS，不新增na。english/age整格、五序列token按大小写不敏感比较；appid不比较该词表，日期只走冻结UTC/coerce/mixed。保留MISSING_EMPTY、MISSING_WHITESPACE、MISSING_DECLARED子类及原字面值；非法非空与合法0各自独立。

english：strip后的字面仅0/1，nullable Int8；1.0/+1/true/True等非法，缺失不补0。required_age：MODE_INT，全匹配[+-]?\d+（Python Unicode十进制数字）；精确整数非负，-0是合法0，12.5/1e2/-0.0等非整数词法非法。存储nullable Int64超容量阻断；0..Int64max是存储域，不是语义年龄上界。Inf非有限、NaN按声明缺失、na非法。不补值、不裁剪，非法特征阻断整包并保留原触发值。

年龄首要诊断依候选PP-AGE-00/01顺序：缺失→显式±inf/infinity(NON_FINITE)→整数词法；小数/指数形式报NON_INTEGER且不转换，其他文本报UNPARSEABLE；精确整数负非零报NEGATIVE，非负超Int64存储容量报OUT_OF_INT64。MODE_FLOAT的OVERFLOW/UNDERFLOW保留代码但当前不输出。词法长串应按十进制量级检查/有界精确转换，不因解释器整数转换字符上限静默放行或删值。

ratings独立规则：pos/neg strip后全匹配ASCII [0-9]+，Int64非负；sum前检查negative不大于Int64max-positive。基础人口仅有效UTC日期且非2019，不加键/特征/ratings合法性过滤。基础人口任一非法ratings或无法比较，阻断且保留完整人口数；cutoff不可计算时写computable=false及null，不删坏行重算、不生成无依据0。基础人口外（NaT/2019）的ratings异常只作诊断。ratings字面域不推广到年龄/其他整数。

## 五序列与源态

developer/publisher/platforms/categories/genres按分号拆，逐token trim、丢空/声明缺失词、按原拼写保留首见去重，实体大小写敏感。逗号/竖线/括号/引号是字面字符，不新增语法；未知token保留并记账。config的case_insensitive_exact_token固定解释为casefold()后完整token匹配windows/mac/linux（候选PP-MV-05/06），notwindows不会命中；Windows;windows count为2但has_windows为true。缺失词仍依lower()比较，不把casefold用于实体去重或改写原拼写。

在任何有损helper之前捕获源状态。源空串、纯空白或所有非空token均为声明缺失，归S_MISSING；交付值为JSON null，源子类另存态旁表source_missing_classes。参与has/count及历史时把逻辑缺失视为空序列，所以has为False、count为0。非缺失纯分隔符等解析为零实体则S_EMPTY_LIST、JSON []；非空实体则S_LIST、JSON字符串数组。丢空后不会产生['']；S_EMPTY_STRING_ELEMENT仅是表示层保留槽位/合成编码例，正式源解析不可输出。null与[]的磁盘表示始终可区分，不能先折叠再反推态。标量缺失不套序列四槽位。

## 日期、人口与来源窗口

UTC=True/errors=coerce/format=mixed保持冻结，偏移按UTC年份归属；NaT保留原值、身份和诊断，标签空且不进开发X/y，不删记录。所有有效非2019行仍属逐年基础人口，包括未覆盖年份；晚于2018且非2019的行隔离、保留该年人口/cutoff统计，不交付其开发标签。人口合计和开发合计分别定义。

历史继续严格较早发行年、任一实体匹配来源游戏并集去重、alpha10/prior0.10、log1p计数；2018来源可包含2017，封顶2016备选不采用。2018仅应用已采用规则，不用于重选词表/语法/阈值；没有学习型imputer/词表/编码器fit。

## 实施与证据边界

本合同与[交接合同](DATA_HANDOFF_CONTRACT.md)/[字段字典](data_contract/field_dictionary.csv)闭合。[53条P05索引](data_contract/assertion_index.json)保留原ID与历史用例内容，只有已采用口径作为当前标准，备选未启用。当前独立v1.2解析与实际合成、真实文件验收已经完成；旧H04的classify/helper仅保留为冻结历史测试，不用于正式交接。

本轮只读真实证据已核对六表字节和字面域，年龄最大18仅当前快照观察；实体引号/分号风险只记账，不改变冻结语法。实际数值/哈希/范围见[正式验收摘要](DATA_HANDOFF_ACCEPTANCE.md)，完整证据随私下交接包提供，不以文档旧NA统计或静态接受冒充新规则运行。2026-10-12的R4仅修正文档阶段与入口；随后R5修复长字段与长前导零键的读取实现，解析规则未改变，原正式包封存正文不回写。
