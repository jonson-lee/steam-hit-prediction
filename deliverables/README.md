# 微信发送说明

只需发送本目录下的 `Steam_Modeling_Handoff_v1.2_2026-10-12.zip` 一个文件，ZIP内已有正式数据、读取代码、完整字典/合同、验收证据及项目展示材料。接收同学无需先下载GitHub或另收散落CSV。

解压后进入项目根目录，先读`docs/MODELING_HANDOFF.md`，运行`python -B -m scripts.load_modeling_data`。ZIP内`SHA256SUMS.json`记录每个内容文件的校验值。

可复制给同学的说明：

> 数据部分已按小组冻结标准完成。请使用压缩包里的正式读入入口，不复用旧STEP1标签或切分。train/validation/test分别为10,345/6,357/8,160行，每组24项原始主特征；词表、编码、补值和标准化请仅在训练数据fit。交接指南有完整字段解释及Python例子，reports/eda里有展示图表。2018已经做过描述性EDA，后续实验请记录这一点。

后续重新制作：在项目根运行`python -B -m scripts.build_modeling_handoff`。默认不覆盖已有ZIP，需用`--output`指定新的文件名。我们未直接发送微信消息。
