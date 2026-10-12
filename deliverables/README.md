# 微信发送说明

当前请发送本目录下的 `Steam_Modeling_Handoff_v1.2_2026-10-12_bilingual.zip` 一个文件，ZIP内已有正式数据、修复后的读取代码、完整字典/合同、独立验收证据、项目展示材料及中英文元数据对照表。新版保留R5长键/长字段及R6的UTF-8/逐源身份切分修复，并补齐非法源行号的阻断诊断（R7）。接收同学无需先下载GitHub或另收散落CSV。原始版、`reader_fix`和`handoff_fix`版均保留为历史版本，正式21文件保持原字节。

解压后进入项目根目录，先读`docs/MODELING_HANDOFF.md`，运行`python -B -m scripts.load_modeling_data`。ZIP内`SHA256SUMS.json`记录每个内容文件的校验值。

中文查阅表在`data/processed/Steam_数据交接中英文对照表.xlsx`，含列名、文件用途、缩写/状态、列表词条和JSON键五张工作表。它位于封存包外，只供解释；不要据此重命名机器列或翻译类别原值。

可复制给同学的说明：

> 数据部分已按小组冻结标准完成。请使用压缩包里的正式读入入口，不复用旧STEP1标签或切分。train/validation/test分别为10,345/6,357/8,160行，每组24项原始主特征；词表、编码、补值和标准化请仅在训练数据fit。data/processed里的中英文对照表解释各文件、列名和状态码，交接指南有Python例子，reports/eda里有展示图表。2018已经做过描述性EDA，后续实验请记录这一点。

后续重新制作：在项目根运行`python -B -m scripts.build_modeling_handoff --output deliverables/新的文件名.zip`。默认不覆盖已有ZIP。我们未直接发送微信消息。
