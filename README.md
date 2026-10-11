# Steam Game Hit Prediction | Steam 游戏爆款预测

IBA6102 Machine Learning for Business 小组项目：用游戏属性和厂商历史进行候选游戏筛选与排序。**数据阶段已完成，建模尚未启动。** 当前政策为v1.2，业务规则保持2026-09-24会议冻结v1.1。

建模同学先读[交接指南](docs/MODELING_HANDOFF.md)，项目展示先读[EDA摘要](docs/EDA_SUMMARY.md)，本次更新见[CHANGELOG](CHANGELOG.md)。GitHub保存实现、测试和标准文档；正式数据、验收原始证据与展示图表由微信交接ZIP提供。

## 文件结构

```text
config.py                      唯一版本化业务/数据政策配置
src/                           解析、交接验证、数据审计与路径管理
scripts/                       数据读入、EDA复现、验收和打包入口
tests/                         当前测试及冻结的历史基线
docs/                          建模交接、标准、字段字典和验收摘要
data/processed/                正式封存数据和验收证据（仅私下交接）
reports/eda/                   展示报告、21张表和5对PNG/SVG（仅私下交接）
deliverables/                  发给建模同学的完整ZIP（仅本地）
outputs/                       以后复现运行的新UTC目录（仅本地）
Project_Proposal_Steam_Game_Success.md  商业问题与方法计划
CHANGELOG.md / JOURNAL.md       GitHub更新日志 / 团队进展摘要
```

详细保留范围见[文件指南](docs/FILE_GUIDE.md)。旧STEP1、协作实验、候选稿、重复candidate和历史运行目录已清除；必要测试fixtures保留。

## 建模交接

解压微信ZIP，进入解压后的项目根目录，安装当前数据依赖并验证读入：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -B -m scripts.load_modeling_data
```

应得到train **10,345**行、validation **6,357**行、test **8,160**行，每份X为**24列**。开发域共24,862行、2,500正类；2019的2,213行隔离。只克隆GitHub时需要另行取得交接ZIP中的`data/processed/`，不能直接从空数据目录开始训练。

读入入口先核验物理READY和文件哈希，严格解码CSV/JSON，按appid对齐X/y/切分元数据。它不拟合、训练或评估模型。

## 冻结标准

- 主标签：同发行年评论总量linear q90，包含边界`>=`，保留早期小cohort。
- 时间切分：train≤2016、validation=2017、test=2018；全部2019排除，禁止随机切分。
- 历史：多厂商按`;`拆分，严格较早发行年游戏取并集去重；alpha=10、prior=0.10。count已做log1p，不再重复转换。窗口A的2018历史包含2017，模型与规则比较须统一窗口。
- X仅24项白名单。appid、split、日期/年份元数据、标签及审计字段不作为预测变量；ratings、owners、playtime、SteamSpy tags/tag_count禁止进入X。price、achievements和辅助快照仅属后续敏感性分析。
- 学习型填补、词表、one-/multi-hot、标准化仅在训练历史fit；参数和阈值在validation选择。报告AP/PR-AUC、ROC-AUC及Top10% precision/recall/lift，单独报告未见厂商表现。

2018的描述性分布与标签人口已查看，须在后续记录中披露。2019单次快照支持回顾性筛选，不能证明真实发售前信息齐备，也不建立销量、因果效果或ROI结论。

## 验收与复现

[正式验收摘要](docs/DATA_HANDOFF_ACCEPTANCE.md)记录18个稳定文件、3个控制文件和独立消费者结果。整理后保留正式21文件原字节，不重新生成READY。

完整合成验收及测试须在Git克隆仓库执行，测试会记录真实HEAD；微信ZIP不包含`.git`。ZIP接收方直接使用上面的只读loader即可。需要复跑验收时，克隆本仓库并把交接数据复制到同名目录。

```bash
python -B -m scripts.run_data_contract_tests
python -B -m unittest discover -s tests -p test_modeling_loader.py -v
python -B -m scripts.reproduce_data_eda --raw-directory /path/to/steam
python -B -m scripts.build_modeling_handoff
```

EDA复现另需六张原始CSV，原始数据不随默认交接ZIP提供。新运行写`outputs/<阶段>/<UTC>/`，不覆盖交接或展示材料。R4固定验收基线仅更新文档阶段和来源指针，保留R3旧绑定；配置、解析/交接实现和旧H04守卫不变。封存包中的合同与config阶段字段是制作时快照，当前完成状态以READY与验收摘要为准。

## 标准与来源

| 内容 | 入口 |
|---|---|
| 会议决定与授权 | [DECISIONS](docs/DECISIONS.md) |
| 当前项目状态 | [PROJECT_CONTEXT](docs/PROJECT_CONTEXT.md) |
| 解析与交接合同 | [解析合同](docs/DATA_PARSE_CONTRACT.md)、[交接合同](docs/DATA_HANDOFF_CONTRACT.md) |
| 实现验收与固定基线 | [实现摘要](docs/DATA_CONTRACT_IMPLEMENTATION.md) |
| 原始数据来源与许可 | [data/README](data/README.md) |
| 商业问题和建模计划 | [项目提案](Project_Proposal_Steam_Game_Success.md) |

数据来源：Nik Davis的[Steam Store Games](https://www.kaggle.com/datasets/nikdavis/steam-store-games)，来源元数据标注CC BY 4.0。小组成员姓名、学号和本机配置不进入公开版本。
