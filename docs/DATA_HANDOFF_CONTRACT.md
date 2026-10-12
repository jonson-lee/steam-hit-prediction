# 数据交接合同 steam-handoff/v1

状态：2026-10-11按用户确认政策定版并接入[交接实现](../src/steam_handoff.py)，正式数据制作及独立消费者验收已完成。config v1.2、业务基底v1.1、parse_policy_ref=steam-parse/v1；机器源[config.py](../config.py)，来源授权[决议D-024至D-028](DECISIONS.md)。68条H05的合成执行证据见[实现记录](DATA_CONTRACT_IMPLEMENTATION.md)；物理HANDOFF_READY已封存，当前状态见[正式验收](DATA_HANDOFF_ACCEPTANCE.md)。

## 文件/schema与字段

[机器schema](data_contract/handoff_schema.json)规定每文件列序、主键、键域、行序、启用条件；[字段字典](data_contract/field_dictionary.csv)逐(file,column)定义角色/类型/缺失/转换/错误路由；[来源映射](data_contract/source_map.csv)、[codebook](data_contract/codebook.json)和[政策快照](data_contract/policy_snapshot.json)共同提供制作输入。JSON单对象无关系主键，内部记录集合各自查键；纯文档对象不强加行序/行数。

仓库schema及152行字典/来源映射是全接口模板，含默认OFF槽位；正式包的schema.files、field_dictionary与source_map须按当次已启用稳定层过滤（包括元数据表自身字段），仅声明实际交付项，不把OFF文件列入manifest.files或要求其存在。

主X仅appid envelope加config.PRIMARY_FEATURE_COLUMNS的24列，顺序/数量/集合全等；appid与态/元数据显式剔除后才是特征。english nullableInt8，age nullableInt64，五序列JSON-in-cell，has_*布尔小写true/false，三个实体count Int64，日历整数Int8、周期与四历史列有限float64。没有学习型展开/fit；任何快照/ratings/outcome/owners/playtime/tags与改名等价物禁主X。raw_parse_values原字面七字段保存在keys_meta，metadata不入X。

x_entity_states含appid、五序列态与source_missing_classes（严格JSON对象；五字段分别PRESENT或MISSING_EMPTY/WHITESPACE/DECLARED）。这是旁表元数据，不增加24主特征。缺失序列值null、派生count0/hasFalse，非缺失空序列[]，reserved空字符串元素不是本源合法输出；标量遵自身schema，不套四槽位。

下表为成功包内稳定层；默认OFF项不出现在实际manifest.files，只有启用后才纳入完整schema/门禁。诊断失败包不称成功。

| 逻辑路径 | 主键/键域 | 必需性 |
|---|---|---|
| handoff/x_primary.csv | appid; developed | required |
| handoff/x_entity_states.csv | appid; developed | required |
| handoff/y_label.csv | appid; developed | required |
| handoff/keys_meta.csv | source_file, source_row_no; all_main_source_records | required |
| handoff/row_disposition.csv | source_file, source_row_no; all_main_source_records | required |
| handoff/rows_excluded.csv | source_file, source_row_no; disposition_excluded_2019 | conditional_required |
| handoff/rows_invalid_unknown.csv | source_file, source_row_no; disposition_invalid_or_uncovered | conditional_required |
| handoff/raw_provenance.csv | source_file, source_row_no; all_main_source_records | optional_OFF |
| handoff/year_cutoffs.csv | release_year; base_population_years | required |
| handoff/history_source_membership.csv | window_variant, target_appid, entity_kind, source_year, source_appid; union_edges | conditional_required |
| handoff/aux_coverage.csv | aux_table; aux_table_names | required |
| handoff/sensitivity_snapshot.csv | appid; developed | optional_OFF |
| manifest/field_dictionary.csv | file, column; delivered_field_definitions | required |
| manifest/source_map.csv | file, column; delivered_field_definitions | required |
| handoff/history_windows.json | 单对象/文档不适用；内部集合见schema; 内部集合 | required |
| manifest/codebook.json | 单对象/文档不适用；内部集合见schema; 内部集合 | required |
| manifest/design_contract_snapshot.json | 单对象/文档不适用；内部集合见schema; 内部集合 | required |
| manifest/handoff_schema.json | 单对象/文档不适用；内部集合见schema; 内部集合 | required |
| manifest/parse_contract.md | 单对象/文档不适用；内部集合见schema; 内部集合 | required |
| manifest/handoff_contract.md | 单对象/文档不适用；内部集合见schema; 内部集合 | required |

所有键域全序明确：appid字符串按ASCII字面序、发行年按精确整数升序、记录身份按source_file再source_row_no数值序、辅助表按aux_table、复合边按schema键逐项比较（year是整数，其余文本按字面）。规范键摘要对有序键数组作严格规范JSON(UTF-8、ensure_ascii=False、allow_nan=False、分隔逗号/冒号)后SHA256，禁裸拼接。正常键与raw键不混用；主表全部记录守恒，辅助表独立审计不并入主行数。

## 字节与读回

新运行仅outputs/data_handoff/UTC微秒时间戳目录，create_run_dir(data_handoff)，不复用覆盖。UTF-8无BOM、不做NFC/NFKC；open newline空串，csv.writer delimiter=逗号/quotechar=双引号/QUOTE_ALL/lineterminator换行。JSON-in-cell用json.dumps ensure_ascii=False、allow_nan=False、separators=(逗号,冒号)，再CSV quoting；禁止分号连接。json.loads以parse_constant拒NaN/Infinity、object_pairs_hook拒重复键，尾逗号拒绝。

标量唯一缺失哨兵为反斜杠N；真实值包括数组元素若恰为哨兵，阻断并升合同版本，不就地转义。读CSV先dtype=str/keep_default_na=False/na_values仅哨兵，再按字典显式转换；缺失/非法/合法0不可吸收，禁静默coerce/默认填充。JSON文件直接严格JSON解码。float64以可往返十进制输出（如Python repr），存储往返精确；独立公式核算绝对误差容许1e-12并记录实值，不用于放宽键/整数/标签判据。

CSV读取使用与原始输入相同的`csv_field_limit()`，完整迭代期间提升字段上限并在正常/异常退出时恢复，不以默认131,072字符截断或拒绝长字面值。消费者appid复用`parse_appid()`核验精确量级，同时要求解析结果等于已交付的规范字符串；保留长前导零，非规范空白键仍拒绝，不修改全局整数转换限制。

合同JSON、候选JSON及封存manifest/report/READY/schema均显式以UTF-8读取，不依赖操作系统默认编码；打包及EDA入口采用相同读法。非UTF-8默认locale不得把合法交接字节误判为校验失败。

## 主去向、cohort与全行对账

主表源记录恰一个source_file/source_row_no身份，keys_meta与row_disposition身份相等。主disposition依config顺序取首命中：invalid_key、invalid_date_nat、excluded_2019、uncovered_year、invalid_label_input、train、validation、test；全部命中原因另存failure_codes，年份/日期/ratings诊断计数与主去向计数分别记录。无更高优先级才取各类去向。bad key不参加appid/raw_appid join，但必须以记录身份参与诊断对账。

keys_meta.split仅从主disposition映射：train/validation/test同值，excluded_2019→excluded，其余invalid_key/invalid_date_nat/uncovered_year/invalid_label_input→unknown；codebook.split_by_disposition逐字相同。制作门禁按每条源身份将keys_meta.disposition和split逐条绑定到独立重算的主去向；元数据内部自洽或全局计数相同不能替代这一核对。敏感性接口默认OFF，其source_defined列是未启用接口槽位；若以后开启，须先形成具体来源/类型/缺失/转换schema再验收，不得以占位类型判通过。

rows_excluded与rows_invalid_unknown由主disposition过滤，零行仍保留表头；四invalid/unknown类各自守恒。排除年/NaT/未知年不在X/y、不交付标签，原值/记录不丢。X/y/态旁表在开发域键集相等，join按appid，载荷各按自身schema，不要求X/y所有字段相等。

基础人口仅有效UTC日期且非2019；cohort_n与cutoff人口相等，不加任何键/特征/ratings过滤。非法基础ratings导致整包阻断，保留人口且computable=false/cutoff null，不能删行重算。可计算时逐年linear q90/inclusive>=与小cohort保留严格来自config。year_cutoffs人口positive_n与开发positive_n各自合计，只有全部人口合法进入开发域才可相等；未知年份保留完整人口统计但不交付开发标签。基础人口外非法ratings仅诊断。

ratings解析和加法保持精确Int64；分位切点及标签比较沿冻结v1.1的pandas quantile/Series.ge口径。近Int64上界的浮点切点取舍沿现有pandas行为，不改用Python标量整数与浮点比较；可计算非空cohort至少一个正类，上界单例/并列另有回归。

## 历史完整来源重建

只用窗口A。membership是每目标/字段/窗口的并集边，主键(window_variant,target_appid,entity_kind,source_year,source_appid)，同一来源可用于多目标/两字段，单主键内不按命中的多个实体重复。独立从目标和来源实体文本重建全部严格較早、非排除年、有有效标签且符合窗口的来源集合，与实际双向逐项对比，分别报缺源/多源/重复，不能只审已有边。

来源标签/实体文本绑定实际y_label/x_primary hash，source_appid与target_appid分别按正确身份join。N、H由独立重建集合计算，log1p(N)、(H+10×0.10)/(N+10)、空集0/0.10核对；不取被测输出中间值。history_windows的target_windows键(window_variant,target_appid,entity_kind)，每目标/字段记录source_years/source_max_year（空集null），cohort_windows再按(window_variant,release_year)汇总。history_windows只可hash其他数据文件，不含自身/上层hash。

## 封存、报告与消费者

candidate文件与最终列序/编码/行序/路径尾名同构，只前缀不同。准备期先检查candidate；封存稳定层进handoff/manifest并逐文件核对与候选字节一致；冻结manifest.files只hash已启用稳定层；生成绑定manifest hash的report；生成READY前所有适用前置通过才最后写READY双hash。manifest不含自身/report/READY hash，report不含自身/READY hash，稳定层不含上层反向hash，任何循环禁止。

manifest必须列实际版本/config/相关源码hash（dirty树不能只记HEAD）、六输入实测指纹、实际UTC与适用依赖版本、每文件schema/列序/键域/行序/行数/hash、disposition/人口/cutoff/窗口、来源绑定与执行证据。unknown null不得当通过；parse与handoff合同正文/schema/字典/来源图/codebook/design快照都属于稳定层。机器schema文档不是manifest，不内嵌自身hash。

report逐条记录H05的PASS/FAIL/BLOCKED/NOT_APPLICABLE、观测数值与证据hash；失败允许局部真实PASS，但overall不得通过、不得可交接、不得READY。scope synthetic与real-file明确。B05政策及只读证据不构成H05 PASS，旧输入指纹不相等时不能冒用旧计数。旧H04退出4语义保留。

消费者在READY写后独立核验：必需文件齐全；稳定层实测hash等manifest；manifest hash等report/READY绑定；report hash等READY绑定；report scope real-file且overall pass；无适用BLOCK或必要政策未决；READY双hash一致。结果另存包外记录，绝不回写封存report。七项有一不成立即包未完成，candidate/残留handoff不得被指针称已验收。CURRENT_HANDOFF默认OFF，无上传/发布权限扩展。

## 实现验收前置

[68条H05索引](data_contract/assertion_index.json)保留原ID与历史提案状态，实际执行结果单独落盘。新增[验收入口](../scripts/run_data_contract_tests.py)运行53P05/68H05及相关回归，固定[新版基线](../tests/fixtures/v12_baseline.json)。旧H04测试与其SHA守卫不改，通过[冻结v1.1配置](../tests/fixtures/legacy_v11/config.py)在临时副本运行11项；直接用当前v1.2配置运行旧测试仍会拒绝。真实文件制作及验收已按2026-10-11授权完成，2026-10-12交接整理不重新制作或修改封存数据。

B05实现与合成验收由[实现记录](DATA_CONTRACT_IMPLEMENTATION.md)单独记录；真实标签/X/y/历史产物、READY及消费者证据见[正式验收](DATA_HANDOFF_ACCEPTANCE.md)。2026-10-12仅修正文档阶段与入口，不改变交接语义、配置或封存包正文，也不启动建模。
