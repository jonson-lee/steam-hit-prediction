# 正式数据交接验收

2026-10-11按用户授权完成真实六表制作、全部适用门禁、物理READY及独立消费者核验。政策v1.2，解析`steam-parse/v1`、交接`steam-handoff/v1`，业务保持会议冻结v1.1。数据制作及EDA已完成；未启动模型训练、调参或模型评估。接收方按[建模交接指南](MODELING_HANDOFF.md)使用正式包。

## 正式包和人口

正式包本地位置为`data/processed/steam_handoff_v12/`，结构为`handoff/`和`manifest/`。2026-10-12目录整理只迁移封存文件，不修改21个文件原字节；验收记录在本地`data/processed/acceptance/`。这些数据和运行证据随私下交接ZIP提供，不提交GitHub。

制作源为课程原始六CSV，旧STEP1不作为来源。主表27,075条源身份全守恒；制作和消费当次原始六表及旧STEP1的26文件保护SHA256前后相同。

| split/去向 | 行数 | 正类 |
|---|---:|---:|
| train（≤2016） | 10,345 | 1,046 |
| validation（2017） | 6,357 | 637 |
| test（2018） | 8,160 | 817 |
| 开发合计 | 24,862 | 2,500 |
| excluded_2019 | 2,213 | 不交付标签 |
| invalid/unknown | 0 | 不适用 |

主X为appid关联键加24白名单特征；X/y/态旁表严格按appid对齐，标签及元数据不入X。22个完整年度人口计算linear q90和inclusive标签，小cohort保留。正式18项稳定文件的schema、字典和来源映射闭合，实际字段定义117项；默认OFF项不进入manifest。

窗口A独立重建169,878条历史边、49,724个目标字段窗口和22个年度窗口。缺源、多源、重复、公式和窗口错误均0，最大公式误差0.0；2018使用2017历史的边28,138条。规则为严格较早年份、并集去重、alpha10/prior0.10/log1p，没有学习型fit。快照敏感性、raw_provenance、窗口B及CURRENT_HANDOFF均OFF。

## 门禁、消费者与封存

`manifest/validation_report.json`为`scope=real-file`、`overall=pass`；68个H05中66 PASS、2 NOT_APPLICABLE仅表示READY后的消费者阶段。全部适用前置通过后写物理`manifest/HANDOFF_READY.json`。稳定层→manifest→report→READY为单向hash，不含反向循环。

未参与制作或修复的独立消费者在两个新Python进程核验：正式7/7、额外实算29/29通过，退出码均0。使用物理READY和`require_real=True`，未传虚拟marker；schema、字节、键摘要、源身份、完整人口标签和全历史来源实算一致。消费者核验前后封存21文件树不变。

H05-GATE-05/06后验PASS另存包外`consumer_acceptance.json`，不回写封存report。`independent_audit.json`和`official_consumer.json`保留详细结果；相关执行记录绑定stdout/stderr、退出码、时间及脚本hash。

| 控制文件 | SHA256 |
|---|---|
| manifest.json | 575032301e0a9433f8d0acb6e93c30e89f27840edc9612c6daed68aa12b65a1d |
| validation_report.json | b39648d690ee594e8a9f5e404d6d8b9d5d42b2248d276ba8fe9164a4cfae791a |
| HANDOFF_READY.json | 308595393b577866ec2e9b239fd65c332031ed85ae3a618eac97f2f746d9f763 |

## 实现版本和整理边界

真实制作必要修复已在R3显式绑定：SteamSpy原生appid适配及真实规模历史验收扫描；业务规则和版本不变。前置旧H04 11/11、当前150/150合成测试通过，零失败、错误或跳过；真实制作执行171.517秒、退出0。详见[合同实现与测试基线](DATA_CONTRACT_IMPLEMENTATION.md)。

R4仅修正仓库当前合同的阶段说明及断链来源，并显式保留R3 prior_binding；config、实现、测试和封存21文件不变。封存包携带的是制作当次合同及其hash，不能用后来仓库合同替换。接收方先核验包内manifest/report/READY，再通过读取工具读取X/y。

EDA的21张汇总表、5对PNG/SVG和STEP1修正保留于本地`reports/eda/`。2018已做描述性查看，未据此调规则或参数，建模应记录这一历史。单次2019快照仅支持回顾性筛选证据，不能推出销量、因果效果或ROI。

## 2026-10-12整理后复核

正式21文件原字节迁移后，消费者读检仍通过；新读取入口11项测试通过，实际读取三个split计数及24列特征一致。R4文档绑定合成复跑旧11/11、当前150/150通过；EDA新入口21/21通过，21数值表和5PNG字节一致。完整记录在私下交接的`data/processed/acceptance/`。建模、训练、调参及模型评估未启动。
