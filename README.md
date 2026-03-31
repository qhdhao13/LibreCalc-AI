# LibreCalc AI（国产混元增强版）

> 仓库目标地址：**[github.com/qhdhao13/LibreCalc-AI](https://github.com/qhdhao13/LibreCalc-AI)**（推送说明见文末）

> 在 **LibreOffice Calc** 里，用自然语言 **读表、写公式、改样式、做图表**——像给表格装了一个听得懂人话的「副驾驶」。

![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)
![LibreOffice](https://img.shields.io/badge/LibreOffice-%206.0%2B-green)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue)

本仓库在优秀开源项目 **[LibreCalc AI Assistant](https://github.com/palamut62/libre_calc_ai_addon)**（原作者 [palamut62](https://github.com/palamut62)）基础上，**接入腾讯混元（Hunyuan）OpenAI 兼容接口**，并针对 **macOS + Python 3.9** 等环境做了**可直接安装运行**的修复与打包说明；同时补充了 **Ollama 本地模型工具调用支持**，支持在「云端混元」与「本地大模型」之间一键切换。

---

## 维护者与联系方式

本仓库（混元增强版与相关说明）由 **[@qhdhao13](https://github.com/qhdhao13)** 维护。

| 方式 | 内容 |
|------|------|
| **微信** | `qhdhao`（添加时请注明来意，例如「LibreCalc AI」） |
| **邮箱** | [qhdhao@126.com](mailto:qhdhao@126.com) |

欢迎反馈问题与改进建议；**商用或再发行合作**请先通过上表方式联系并取得同意。

---

## 为什么你会需要它

- **会说人话**：用中文描述需求，例如「把 A1:D1 合并并加粗」「写入求和公式」「检查这片区域有没有公式错误」。
- **真的会改表格**：通过「工具调用」机制驱动 LibreOffice，而不是只给你一段文字说明。
- **数据留在本地**：表格文件仍在你的电脑上；与云端模型的通信只发送你对话和工具执行所需内容（请自行评估合规与脱敏）。
- **离线桥接设计**：LibreOffice 内嵌 Python 负责 UNO 桥 + HTTP 桥，**带界面的 PyQt 子进程**用系统 Python 启动——既避开嵌入式环境缺依赖，又能稳定操作当前工作簿。

---

## 功能亮点（吸睛版）

| 能力 | 说明 |
|------|------|
| **智能读写** | 按区域读值、写文本/数字/公式、清表、复制区域 |
| **颜值与排版** | 字体、对齐、边框、颜色、列宽行高、合并单元格 |
| **数据动作** | 排序、自动筛选、数据验证、条件格式 |
| **可视化** | 依据数据范围创建图表 |
| **工作表** | 列出/切换/新建/重命名工作表 |
| **模型与主题** | 本 fork 主打 **腾讯混元**；仍保留 OpenRouter / Ollama 等上游能力（以源码为准） |

> 一句话卖点：**把「Excel 助手」搬进 LibreOffice Calc，且能接国内云端大模型。**

---

## 快速开始

### 1. 安装扩展

1. 下载本仓库发布页中的 **`libre_calc_ai-1.0.2-hunyuan.oxt`**（或自行从 `_oxt_extracted` 打包，见下文）。
2. LibreOffice → **工具 → 扩展管理器 → 添加** → 选择该 `.oxt`。
3. **完全退出并重启** LibreOffice。

### 2. 配置系统 Python（macOS 重点）

扩展会用 **系统 Python** 启动图形界面，需满足：

- 可 `import PyQt5`
- 可 `import httpx`
- Python **3.9** 用户：本仓库已加入 `from __future__ import annotations` 等兼容，避免 `list[dict] | None` 导入崩溃

建议在 `~/.config/libre_calc_ai/settings.json` 中设置（示例，使用腾讯混元）：

```json
{
  "system_python_path": "/Library/Developer/CommandLineTools/usr/bin/python3",
  "llm_provider": "hunyuan",
  "hunyuan_api_key": "在腾讯云控制台创建，勿泄露",
  "hunyuan_base_url": "https://api.hunyuan.cloud.tencent.com/v1",
  "hunyuan_default_model": "hunyuan-turbos-latest"
}
```

如需使用 **本地 Ollama 模型（以 `qwen2.5:7b` 为例）**，可以在同一个文件中同时保留两套配置，通过 `llm_provider` 一键切换：

```json
{
  "system_python_path": "/Library/Developer/CommandLineTools/usr/bin/python3",
  "llm_provider": "ollama",
  "ollama_base_url": "http://localhost:11434",
  "ollama_default_model": "qwen2.5:7b",
  "hunyuan_api_key": "",
  "hunyuan_base_url": "https://api.hunyuan.cloud.tencent.com/v1",
  "hunyuan_default_model": "hunyuan-turbos-latest"
}
```

将 `llm_provider` 设为 `"ollama"` 即使用本地模型；改为 `"hunyuan"` 并提供有效 `hunyuan_api_key` 即使用腾讯混元。

### 3. 一键补依赖（示例）

```bash
/Library/Developer/CommandLineTools/usr/bin/python3 -m pip install PyQt5 httpx python-dotenv
```

`python-dotenv` 在本 fork 中已改为**可选**；不装也能启动。

### 4. 验证是否成功

在 Calc 中打开 **AI Assistant**，先试：

- 「把当前选中单元格写成 123」
- 「把 A1 加粗、背景设为浅黄色」

若失败，请查看：`~/.config/libre_calc_ai/logs/oxt_bridge.log` 与 `subprocess_stderr.log`。

---

## 从源码自行打包 `.oxt`

在 `_oxt_extracted` 目录下执行：

```bash
cd _oxt_extracted
zip -r ../libre_calc_ai-1.0.2-hunyuan.oxt .
```

**注意**：`Addons.xcu` 中的脚本 URL 必须与最终 `.oxt` **文件名一致**，否则会报 `KeyError`；本仓库内已对齐 `libre_calc_ai-1.0.2-hunyuan.oxt`。

---

## 架构一览（通俗版）

```text
┌─────────────────┐     HTTP 桥      ┌──────────────────────┐
│  LibreOffice    │ ◄──────────────► │  PyQt5 主界面/设置   │
│  (interface.py) │   tools/dispatch │  (系统 Python)       │
└────────┬────────┘                  └──────────┬───────────┘
         │ UNO                                   │ LLM（腾讯混元 / 本地 Ollama）
         ▼                                      ▼
    当前 Calc 文档                         文本/工具调用
```

---

## 致谢

- **核心上游**：[palamut62 / libre_calc_ai_addon](https://github.com/palamut62/libre_calc_ai_addon) —— MIT License  
- **混元接口文档**：[腾讯混元 OpenAI 兼容接口](https://cloud.tencent.com/document/product/1729/111007)

---

## 许可证与使用约定

- **许可证**：本仓库在 **`LICENSE`** 中沿用 **MIT**（含上游版权声明）；另有 **`NOTICE`** 说明衍生来源。
- **个人与非商业开源分享**：欢迎 Fork、学习、自用、在遵守 MIT 的前提下分享改进。
- **商业使用**：若将本仓库或衍生成果用于**对外商业产品、SaaS、再发行收费发行版**等场景，**请先通过本 README「维护者与联系方式」中的微信或邮箱与维护者沟通并取得同意**（便于品牌、责任边界与支持方式达成一致）。  
  *说明：MIT 在法律层面允许商用；此条为维护者倡导的**事先沟通约定**，亦有助于避免误用密钥、数据合规与品牌混淆。*

---

## English (short)

**LibreCalc AI — Hunyuan-ready fork** for LibreOffice Calc: natural-language spreadsheet assistant with tool calling (read/write/format/charts). Adds **Tencent Hunyuan** (OpenAI-compatible) provider plus macOS/Python 3.9 friendliness. Upstream: **palamut62** (MIT). **Maintainer:** [@qhdhao13](https://github.com/qhdhao13) · WeChat `qhdhao` · Email `qhdhao@126.com`. **Commercial use: please contact the maintainer first** (courtesy / coordination; see `LICENSE` for legal terms).

---

<p align="center"><b>Enjoy your spreadsheet copilot.</b></p>

---

## 推送到你的 GitHub（qhdhao13）

在本机项目根目录 **`LibreCalc AI`** 下已经初始化 Git 并完成首次提交。请你**在自己的终端**执行（需已安装 [GitHub CLI](https://cli.github.com/) 并已登录）：

```bash
cd "/Volumes/disk-hfm/LibreCalc AI"
gh auth login
gh repo create LibreCalc-AI --public \
  --description "LibreCalc AI — 腾讯混元增强版 · LibreOffice Calc 自然语言助手" \
  --source=. --remote=origin --push
```

登录账号为 **qhdhao13** 时，上述命令会创建 **`https://github.com/qhdhao13/LibreCalc-AI`** 并推送。

**若不用 gh**：在 GitHub 网页新建空仓库 `LibreCalc-AI`，然后：

```bash
cd "/Volumes/disk-hfm/LibreCalc AI"
git remote add origin https://github.com/qhdhao13/LibreCalc-AI.git
git branch -M main
git push -u origin main
```

**发布安装包**：可将根目录的 `libre_calc_ai-1.0.2-hunyuan.oxt` 在 GitHub **Releases** 里上传，方便他人直接下载安装。
