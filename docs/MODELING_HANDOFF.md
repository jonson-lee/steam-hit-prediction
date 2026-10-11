# 建模同学交接指南

数据部分已完成；解压交接 ZIP 后，从工程根目录使用正式消费入口。正式封存包位于 `data/processed/steam_handoff_v12/`，共有 21 个文件，保留原文件字节及 manifest → report → READY 校验链。建模无需原始六表、旧 STEP1 文件或过程日志。封存包中的合同正文是制作时历史快照，其旧阶段表述与原仓库相对链接不再表示当前状态；阅读本项目`docs/`下的当前合同及指南，不能修写封存正文来更改链接。

## 安装与读取

使用 Python 3.11 或更新版本，在工程根目录安装项目依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -B -m scripts.load_modeling_data
```

最后一条命令只验证正式包并打印三个 split 的行数、特征数和正类数，不拟合任何模型。后续建模所需的模型库由建模同学根据选定方案安装。

可直接复制以下 Python 示例：

```python
from scripts.load_modeling_data import load_modeling_data

data = load_modeling_data()
X_train = data["train"]["X"]
y_train = data["train"]["y"]["hit_reviews"]
X_validation = data["validation"]["X"]
y_validation = data["validation"]["y"]["hit_reviews"]
X_test = data["test"]["X"]
y_test = data["test"]["y"]["hit_reviews"]
train_metadata = data["train"]["metadata"]
train_states = data["train"]["states"]
assert X_train.index.equals(y_train.index)
```

`load_modeling_data(package_dir="其他封存包路径")`也支持显式指定路径。入口首先执行真实消费者校验，再比较封存配置快照与当前 `config.py`，按封存 schema 和字段字典解码 CSV；任何 hash、字段、键域、标签或切分不一致都会报错。

每个 split 返回四个 pandas DataFrame，使用同一个**字符串 appid 索引**，按 appid 重排而不是依赖 CSV 行序。前导零保持，例如 `"001"` 不会变为 `1`。

| 返回项 | 用途 |
|---|---|
| `X` | 恰好 24 个白名单预测字段；appid 只在索引中，不是特征列 |
| `y` | 仅 `hit_reviews` 一列；评论数与标签审计字段不会混入 |
| `metadata` | 名称、发行日期、发行年、split、来源身份及原解析值，供核对与关联 |
| `states` | 五个序列字段的源状态及缺失子类，供缺失处理和解释 |

五个序列字段 `developer`、`publisher`、`platforms`、`categories`、`genres`为 Python list 或 `None`。JSON `null`读为 `None`，JSON `[]`读为空 list；两者保持区别。整数按 schema 使用 pandas nullable `Int8`/`Int64`，布尔值明确解码，JSON对象保持对象。请勿用 pandas 默认 NA 推断重新读取封存 CSV，也不要用分号重新拆分已经解码的序列。

## 冻结的标签、切分与特征

政策版本为 v1.2，业务设计保持 v1.1；`config.py`为唯一机器配置源。[项目上下文](PROJECT_CONTEXT.md)、[解析合同](DATA_PARSE_CONTRACT.md)、[交接合同](DATA_HANDOFF_CONTRACT.md)及封存字典说明完整规则。

主标签为完整发行年度内 `positive_ratings + negative_ratings` 的 linear 90% 分位数，使用 inclusive `>=`；保留小年度 cohort 和切点并列。2019 发行游戏全部排除。

| split | 发行年 | 行数 | 正类 |
|---|---|---:|---:|
| train | ≤2016 | 10,345 | 1,046 |
| validation | 2017 | 6,357 | 637 |
| test | 2018 | 8,160 | 817 |

主 `X` 包括语言、分级年龄、厂商/平台/类别/类型序列、平台布尔及序列计数、UTC月份/季度/星期和周期编码、四个厂商历史特征。`dev_prior_count`与`pub_prior_count`**已经是 log1p(N)，不要重复取 log1p**。历史命中率已经按 alpha=10、prior=0.10 平滑，缺失或未见实体回退次数0、命中率0.10。

评论数、owners、playtime、SteamSpy tags、tag_count及结果派生量禁止进入主 `X`；price、achievements及辅助表快照字段只允许后续单独的敏感性分析。appid、name、release_year、split、标签和任何审计字段也不作为预测变量。`metadata`和`states`不应直接拼接到模型矩阵；若要引入新的缺失指示特征，应先按项目规则明确白名单变更。

## 接续建模约定

- 词表、multi-hot/one-hot、补值、标准化和其他学习型变换仅在 train 拟合，再应用到 validation/test。不要先对全数据拟合词表或补值，不做随机切分或 shuffled CV。
- 历史特征使用窗口 A：仅严格较早发行年份、历史游戏并集去重。2018 历史允许使用2017，封存历史接口已记录。正式模型与规则基准须统一历史窗口；仅用≤2016历史的规则不能与当前滚动窗口结果直接比较。
- 参数、特征方案和阈值使用 validation 选择；test用于最终评估。报告 AP/PR-AUC、ROC-AUC及 Top10% precision/recall/lift，说明评分并列处理，并单报未见厂商表现。
- 数据阶段已经描述性查看2018测试分布、标签人口和EDA图表，未据此选择规则、参数、特征或阈值。后续实验记录须如实承认这一查看历史。
- 2019单次快照支持回顾性筛选原型。主标签衡量观测热度，不等于销量、收入、利润或质量；历史发行年约束不能证明这些历史命中标签在真实发售前已可得，也不能建立因果影响或ROI。

展示材料集中在 `reports/eda/`：`EDA_REPORT.md`、`STEP1_CORRECTIONS.md`、`tables/`、`figures/`和`summary.json`。正式7/7消费者核验和额外29/29历史验收证据保留在本地 `data/processed/acceptance/`；该指南与读取入口不训练模型，也不修改封存文件。

## 可选完整验收

ZIP不含Git历史，只读loader无需Git。若要运行`run_data_contract_tests`或`test_modeling_loader.py`，请先克隆本GitHub仓库，再把ZIP的`data/processed/`和`reports/eda/`复制到同名目录；合成制作测试需要仓库真实HEAD。不要在裸解压目录执行完整制作验收。
