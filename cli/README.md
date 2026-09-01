# IRSTD-AutoLabel CLI

[English](README_EN.md) | **简体中文**

命令行批量标注工具，用于红外小目标检测（IRSTD）的自动评估、可视化和标签导出。CLI 不依赖浏览器，可直接从本地目录读取原图、GT 与预测图，批量生成论文展示图、COCO、YOLO 和统计 CSV。

> 本项目当前只开源命令行实现。网页交互版以在线服务形式提供，网页前后端源码不包含在本仓库中；使用入口见[顶层 README 的 Online web service](../README.md#online-web-service)。

## 功能概览

- 自动识别三类目录结构：`standard`、`sota_flat`、`numbered_flat`
- 支持两种模式：
  - `prediction`：预测图评估，输出 A / B / C 三类结果
  - `original`：原图标注，只基于 GT 生成标注图
- 支持多格式导出：PNG、COCO JSON、YOLO TXT、CSV
- 支持按 `stem`、`model`、`source` 过滤任务
- 支持命令行控制插值方式、框颜色、亮度、对比度、边框宽度和放大图内边距
- A/B 类目标自动生成局部放大图，C 类仅显示主图小框

## 安装依赖

```bash
pip install Pillow
```

在项目根目录运行：

```bash
python -m cli.batch_label_cli --help
```

## 输入目录和文件命名要求

在运行 CLI 前，先确认你的图片目录符合下面任意一种结构。程序会自动检测目录类型，并根据文件名把原图、GT 和预测图配成任务。

支持的图片后缀：

```text
.png, .jpg, .jpeg, .bmp, .tif, .tiff
```

### 结构 1：Standard 目录结构

适合常规数据集。`Original` 放原图，`GT` 放真值图，其他同级目录都视为预测结果来源。

```text
figures/
├── Original/
│   ├── XDU104.png
│   └── Misc_29.png
├── GT/
│   ├── XDU104.png
│   └── Misc_29.png
├── Method_A/
│   ├── XDU104.png
│   └── Misc_29.png
└── Method_B/
    ├── XDU104.png
    └── Misc_29.png
```

规则：

- `Original/` 和 `GT/` 是固定目录名。
- 除 `Original/`、`GT/` 外的子目录会被识别为预测源，可用 `--source Method_A` 指定。
- 文件通过相同 stem 匹配，例如 `XDU104.png` 会匹配 `Original/XDU104.png`、`GT/XDU104.png` 和 `Method_A/XDU104.png`。
- 支持子目录；代码会优先按相对路径匹配，匹配不到时再按同名文件回退。

### 结构 2：SOTA Flat 扁平结构

适合论文对比图。所有图片放在同一个目录下，用数字前缀区分原图、GT 和不同模型。

```text
figures/SOTA_duibi/
├── 0_original_000041.png
├── 1_gt_000041.png
├── 2_Method_A_000041.png
├── 3_Method_B_000041.png
└── 4_Method_C_000041_Pred.png
```

规则：

- `0_...`：原图。
- `1_...`：GT。
- `2_...` 及更大数字：预测图。
- `original_`、`gt_`、`ori_` 这类前缀会在匹配 stem 时自动剥离。
- 预测图命名通常是 `数字_模型名_stem.png`，例如 `2_Method_A_000041.png`。
- 支持 `_Pred` 后缀，例如 `4_Method_C_000041_Pred.png`。

### 结构 3：Numbered Flat 扁平结构

适合消融实验目录。所有图片放在同一个目录下，原图和 GT 通常没有 `original_` / `gt_` 字样。

```text
figures/xiaorong/gcc/
├── 0_Misc_92.png
├── 1_Misc_92.png
├── 2_Method_A_Misc_92.png
└── 3_sigma2_Misc_92.png
```

规则：

- `0_stem.png`：原图。
- `1_stem.png`：GT。
- `2_模型名_stem.png` 及更大数字：预测图。
- stem 可以包含下划线，例如 `Misc_92`。

### 最小可运行条件

每个任务至少需要：

```text
1 张原图
1 张 GT
1 张预测图（prediction 模式）
```

如果使用 `--mode original`，则只需要原图和 GT；不会读取预测图。

## 快速开始

```bash
# 不指定mode参数则默认为预测图模式，处理整个目录
python -m cli.batch_label_cli --input figures/SOTA_duibi

# 原图模式，只根据 GT 在原图上标注目标
python -m cli.batch_label_cli --input figures/SOTA_duibi --mode original

# 只处理一张图和一个模型
python -m cli.batch_label_cli --input figures/SOTA_duibi --stem 000041 --model Method_A
```

## 参数说明

### 基础参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | 必填 | 输入目录路径 |
| `--mode` | `prediction` | 标注模式：`prediction` 或 `original` |
| `--output` | `<input>/output_cli` | 输出目录 |
| `--format` | `all` | 导出格式：`coco`、`yolo`、`png`、`csv`、`all`，可逗号组合 |

### 过滤参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--source` | 无 | 指定预测源，主要用于 `standard` 目录结构 |
| `--stem` | 无 | 按图像 stem 过滤，例如 `XDU104`、`000041`、`Misc_29` |
| `--model` | 无 | 按模型名过滤，例如 `Method_A`、`Method_B` |

### 匹配与框生成参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--threshold` | `3.0` | 中心点距离匹配阈值，单位为像素 |
| `--strategy` | `confidence` | 冲突消解策略：`confidence` 或 `distance` |
| `--adaptive-padding` | `4` | 自适应框额外 padding，单位为像素 |
| `--box-size` | `30.0` | 保留参数，目前核心框大小由 `--adaptive-padding` 控制 |

### 可视化参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--stroke-width` | `1` | 主图小框线宽 |
| `--panel-padding` | `2` | 目标边缘到局部放大图边缘的间距 |
| `--brightness` | `1.0` | 亮度因子 |
| `--contrast` | `1.0` | 对比度因子 |
| `--no-viz` | `False` | 跳过 PNG 可视化，仅导出数据文件 |
| `--verbose` / `-v` | `False` | 打印详细错误堆栈 |

## 插值方式控制

支持的插值名称：

```text
nearest, bilinear, bicubic, lanczos, box, hamming
```

| 参数 | 默认值 | 控制范围 |
|------|--------|----------|
| `--mask-resample` | `nearest` | GT / Pred mask resize 后再做连通域提取 |
| `--base-resample` | `lanczos` | 整张底图缩放到导出分辨率 |
| `--zoom-resample` | `nearest` | 生成局部放大图前的源图放大 |
| `--panel-resample` | `nearest` | 局部 crop / zoom panel 缩放到最终面板尺寸 |

默认插值保持原行为：

- mask：`nearest`
- 局部放大：`nearest`
- zoom panel：`nearest`
- 底图导出缩放：`lanczos`

示例：

```bash
python -m cli.batch_label_cli --input figures/SOTA_duibi \
  --mask-resample nearest \
  --base-resample lanczos \
  --zoom-resample nearest \
  --panel-resample nearest
```

如果希望所有缩放都保留像素块感：

```bash
python -m cli.batch_label_cli --input figures/SOTA_duibi \
  --base-resample nearest \
  --zoom-resample nearest \
  --panel-resample nearest
```

## 颜色控制

颜色支持两种格式：

```text
#RRGGBB
R,G,B
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--color-a` | `#FF0000` | A / True Positive 框颜色 |
| `--color-b` | `#FFD700` | B / False Alarm 框颜色 |
| `--color-c` | `#00BFFF` | C / Miss 框颜色 |
| `--color-gt` | `#FF0000` | `original` 模式下 GT 框颜色 |

模式对应关系：

- `--mode prediction` 使用 `--color-a`、`--color-b`、`--color-c`。
- `--mode original` 只使用 `--color-gt`，不会读取 `--color-a`、`--color-b`、`--color-c`。

示例：

```bash
python -m cli.batch_label_cli --input figures/SOTA_duibi --stem 000041 --model Method_A \
  --color-a "#00FF00" \
  --color-b "255,128,0" \
  --color-c "#3366FF" \
  --color-gt "#FF00FF"
```

原图模式改色示例：

```bash
python -m cli.batch_label_cli --input figures/SOTA_duibi --mode original --stem 000041 \
  --format png,csv \
  --color-gt "#00FFFF"
```

## 常用示例

### 匹配调优

```bash
# 增大中心点匹配阈值
python -m cli.batch_label_cli --input figures/SOTA_duibi --threshold 5

# 距离优先，而不是置信度优先
python -m cli.batch_label_cli --input figures/SOTA_duibi --strategy distance
```

### 可视化调优

```bash
# 提高亮度和对比度
python -m cli.batch_label_cli --input figures/SOTA_duibi --brightness 1.2 --contrast 1.15

# 增大主图小框线宽和 zoom panel 内边距
python -m cli.batch_label_cli --input figures/SOTA_duibi --stroke-width 2 --panel-padding 4

# 改变自适应框 padding
python -m cli.batch_label_cli --input figures/SOTA_duibi --adaptive-padding 8
```

### 导出控制

```bash
# 只导出 PNG 和 CSV
python -m cli.batch_label_cli --input figures/SOTA_duibi --format png,csv

# 只导出 COCO / YOLO / CSV，不生成 PNG
python -m cli.batch_label_cli --input figures/SOTA_duibi --no-viz --format coco,yolo,csv

# 指定输出目录
python -m cli.batch_label_cli --input figures/SOTA_duibi --output results/
```

### 完整组合示例

```bash
python -m cli.batch_label_cli --input figures/SOTA_duibi --stem 000041 --model Method_A \
  --format png,csv \
  --threshold 3 \
  --strategy confidence \
  --adaptive-padding 4 \
  --stroke-width 1 \
  --brightness 1.1 \
  --contrast 1.1 \
  --mask-resample nearest \
  --base-resample lanczos \
  --zoom-resample nearest \
  --panel-resample nearest \
  --color-a "#FF0000" \
  --color-b "#FFD700" \
  --color-c "#00BFFF"
```

Windows PowerShell 可用反引号换行：

```powershell
python -m cli.batch_label_cli --input figures\SOTA_duibi --stem 000041 --model Method_A `
  --format png,csv `
  --mask-resample nearest `
  --base-resample lanczos `
  --zoom-resample nearest `
  --panel-resample nearest `
  --color-a "#FF0000" `
  --color-b "255,215,0" `
  --color-c "#00BFFF"
```

## 输出结构

```text
<input>/output_cli/
├── summary.csv
├── coco/
│   ├── Method_A_XDU104.json
│   └── ...
├── yolo/
│   ├── Method_A_XDU104.txt
│   └── ...
└── visualizations/
    ├── Method_A_XDU104.png
    └── ...
```

## 结果类别

预测图模式：

- `A`：True Positive，预测目标与 GT 匹配成功，默认红色
- `B`：False Alarm，预测目标未匹配到 GT，默认黄色
- `C`：Miss，GT 未被预测目标匹配，默认蓝色
- A / B 类会生成局部放大图；C 类只在主图显示小框

原图模式：

- 使用 GT 目标在原图上生成标注框，默认红色
- 原图模式的框颜色由 `--color-gt` 控制；`--color-a`、`--color-b`、`--color-c` 只影响预测图模式
- 每个 GT 目标都会生成局部放大图

## 固定常量

以下仍是代码常量，当前未提供命令行参数：

| 常量 | 当前值 | 说明 |
|------|--------|------|
| `ZOOM_PANEL_SIZE` | `188` | 局部放大图基础面板尺寸 |
| `DEFAULT_ZOOM_BORDER_WIDTH` | `8` | 局部放大图边框宽度 |
| `EXPORT_LONGEST_SIDE` | `960` | 导出图最长边 |
| `ZOOM_GROUP_DISTANCE` | `20` | 近距离目标合并为同一放大图的阈值 |

## 验证命令

```bash
python -m cli.batch_label_cli --help
python -m cli.batch_label_cli --input figures/SOTA_duibi --stem 000041 --model Method_A --format png,csv
```
