# Japanese Diet：公开数据抓取与分析

Python 3.11+ 项目，依据附带的 `source/Japanese Diet.pptx`。使用 requests 请求公开数据、BeautifulSoup 解析官方 HTML、NumPy 计算描述统计、SciPy 计算相关系数。没有生成模拟数据，也不会用 PPT 数字填补抓取失败。

## 运行

在本目录打开终端。Windows PowerShell：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe project.py all
```

macOS / Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python project.py all
```

需要联网；无需 API 密钥。可分步运行：

```sh
python project.py extract
python project.py fetch --start 2000 --end 2022
python project.py analyze
```

以上 `python` 指虚拟环境中的解释器。默认截止 2022 年，以靠近 PPT 的 World Bank (2022) 引用；这不代表能恢复当年数据库版本。若要延伸，使用 `--end 2024` 等参数。World Bank 可能修订历史值，当前抓取值与旧图不一致并不必然是错误。

## PPT 数字与来源边界

`data/ppt_income.csv` 保存第 4–5 页原值，不覆盖：日本中位数 5,670,000 JPY，美国中位数 83,600 USD；第 5 页日本 Q1/中位数/Q3 为 26,994 / 37,422 / 56,628 USD，美国为 60,300 / 83,600 / 127,000 USD。PPT 换算率为 1 JPY = 0.0066 USD；算术核对 5,670,000 × 0.0066 = 37,422，不把该汇率当作当前汇率。

第 17 页给出 SalaryExplorer 域名，但没有具体页面、统计年份、样本或年/月收入口径。因此原值标为未核实；不能称为官方家庭收入，不能从这些分位数推造工资样本，不能拿三个分位点做 t 检验。`ppt_text.json` 保留 19 页可提取文本，原 PPT 也完整附带。

第 14、18 页引用 World Bank 出生时预期寿命，检索日写作 2025-03-08。图中图片/截图未自动 OCR，故项目没有声称读出了图上的所有数值；原图保留在 PPT 中。第 17 页参考资料所称“Page 2&3”与实际收入页 4–5 不一致，项目使用实际幻灯片页码。

## 公开数据

| 数据 | 来源 / 定义 | 用途 |
|---|---|---|
| 预期寿命 | [World Bank SP.DYN.LE00.IN](https://data.worldbank.org/indicator/SP.DYN.LE00.IN)，出生时总预期寿命（年） | 日本、美国、世界，逐年比较 |
| 人均国民收入 | [NY.GNP.PCAP.CD](https://data.worldbank.org/indicator/NY.GNP.PCAP.CD)，Atlas method，当前美元 | 日本、美国、世界；补充宏观收入指标 |
| PPP 人均国民收入 | [NY.GNP.PCAP.PP.CD](https://data.worldbank.org/indicator/NY.GNP.PCAP.PP.CD)，当前国际元 | 同口径收入与寿命的描述性相关 |
| 美国家庭收入 | [Census Income in the United States: 2023](https://www.census.gov/library/publications/2024/demo/p60-282.html) | HTML 提取 2023 年实际家庭收入中位数，2023 美元 |
| 日本家庭收入 | [厚生劳动省 2023 年国民生活基础调查：所得](https://www.mhlw.go.jp/toukei/saikin/hw/k-tyosa/k-tyosa23/dl/03.pdf) | PDF 提取全世带平均所得；调查年 2023，收入年 2022；万円转 JPY |

World Bank 使用其[官方 Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation)。日本平均家庭收入和美国家庭收入中位数具有不同统计量、年份及货币，分别保存，不能直接做高低排名或相减。国民收入是宏观统计，也不是工资或家庭收入。PPP 当前国际元未消除跨年价格变化。

## 输出与审计

- `data/world_bank.csv`：指标、国家、年份、原始值、单位、URL、数据库更新日期。空值保留为空，不插值。
- `data/official_income.csv`：官方网页/PDF 抽取值及上下文证据；网页结构改变时记录解析失败，不硬编码替代值。
- `data/raw/`：实际下载的 JSON、HTML、PDF、提取文本。
- `data/manifest.json`：UTC 请求时间、最终 URL、HTTP 状态、SHA-256、抓取/解析错误。
- `data/analysis.json`：寿命首末值、跨年均值、变化、日本减世界寿命差、按共同非空年份配对的 Pearson / Spearman 系数；PPT 换算及 IQR 单列。

请求有超时和有限重试，不绕过访问限制；单个来源失败仍保留其他结果，并以非零退出码提示。排错先看 manifest；离线可直接运行 `analyze` 使用已附带的真实抓取快照。重新 `fetch` 会覆盖该次结果及 manifest，要保留旧版本请先复制 `data/`。

## 分析限制

跨年均值是年度指标的均值，不是人口加权个人寿命均值；相关系数仅作探索，时间趋势与自相关会影响解释，因此不报告依赖独立样本假设的显著性检验。分析不证明日本饮食导致长寿，也没有个体饮食、死亡原因或混杂因素数据。不可将国家层面相关用于判断个人健康风险。

