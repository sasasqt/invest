# Primary-source financial factor-mining catalog

Retrieved October 5, 2026, after scholarly network access became available. This catalog records **primary abstract evidence**, not reproduced experiments. Selected method and evaluation sections were also read for the papers identified in the [literature review](LITERATURE_REVIEW.md).

Discovery query: `(all:"alpha mining" OR all:"formulaic alpha" OR all:"factor mining") AND (cat:q-fin.* OR cat:cs.* OR cat:stat.*)`, sorted by submitted date, maximum 80 results. The API returned 54 records; 49 relevant or adjacent records were retained. Searches by additional titles and proceedings metadata supplemented this query. This is a bounded search and does not establish exhaustive coverage.

Preprints and venue publications may have different titles and versions. Dates below come from API metadata; versioned URLs identify the retrieved records. Abstract excerpts describe author claims and may omit qualifications.

## Catalog

### From Search to Research: Exploring Search Scaling in Autonomous Quantitative Factor Mining

- Source: [2609.35559v1](https://arxiv.org/abs/2609.35559v1)
- Authors: Kangcheng Deng, Hui Cai, Jiacheng Lu, Chester Zhongshu Qian, Rui Sun, Beidi Luan, Jing Li, Daxin Jiang, Zuo Bai
- API publication date: 2026-09-28; latest retrieved update: 2026-09-28.
- Abstract excerpt: Inference scaling has been shown to improve large language model (LLM) performance, and this principle naturally extends to autonomous LLM agents through increased search budgets, which we refer to as *search scaling*. Although prior work has characterized the mechanisms, scaling behavior, and performance limits of LLM inference scaling, much less is known about these questions in autonomous research. Therefore, we investigate how search scaling affects research performance and what mechanisms drive these gains using 50 quantitative…

### AlphaPareto: Formulaic Alpha Discovery with LLM-Guided Multi-Objective Reinforcement Learning

- Source: [2609.34188v1](https://arxiv.org/abs/2609.34188v1)
- Authors: Yingbo Zhao, Zeyu Yang, Zhoufan Zhu
- API publication date: 2026-09-28; latest retrieved update: 2026-09-28.
- Abstract excerpt: Formulaic alpha discovery is a core challenge in quantitative trading, as identifying alphas that work well together remains difficult. Recent reinforcement learning (RL) methods formulate this task as a Markov decision process (MDP), but two important issues remain unresolved. First, as the alpha pool evolves, the reward function changes accordingly, making the MDP inherently non-stationary. Second, most existing methods optimize a single objective, typically predictive power, while ignoring other important properties of a high-quality alpha…

### AlphaDiverse: Post-Training Local Quantitative Research Agents for Diverse Exploration in Alpha Factor Mining

- Source: [2609.29014v1](https://arxiv.org/abs/2609.29014v1)
- Authors: Qingzhuo Wang, Zikun Wei, Zhihua Wei, Wen Shen
- API publication date: 2026-09-24; latest retrieved update: 2026-09-24.
- Abstract excerpt: Large language model (LLM)-based multi-agent systems can automate alpha factor mining, but their reliance on external APIs limits control over cost, availability, and confidentiality. Long research loops also tend to revisit a few successful economic mechanisms that lead to research path collapse. To address these limitations, we propose AlphaDiverse, a framework that integrates a multi-agent alpha research system, diverse research path collection, and post-training for local agents. We let the research system generate complementary plan…

### AlphaRJM: Reward-Jump Memory for Stochastic Return-Guided Alpha Discovery

- Source: [2609.08581v1](https://arxiv.org/abs/2609.08581v1)
- Authors: Sayan Dhan, Selvaraju Natarajan
- API publication date: 2026-09-08; latest retrieved update: 2026-09-08.
- Abstract excerpt: Formulaic alpha discovery is a pool-dependent symbolic search problem in which informative feedback is observed primarily when a complete expression is evaluated. This delayed feedback creates two coupled difficulties: the retained alpha pool does not preserve the full history of realized evaluation feedback, and the value of an intermediate construction action is uncertain because its consequence depends on the formula eventually completed. We introduce AlphaRJM, which addresses these difficulties through Reward-Jump Memory, an event-driven…

### Agentic Quantitative Trading: A Survey of Workflows, Systems, and Evaluation

- Source: [2608.31041v1](https://arxiv.org/abs/2608.31041v1)
- Authors: Fengrui Hua, Hengyi Yang, Xinlei Hao, Haohan Zhang, Bokai Cao, Yiyan Qi, Jia Li, Jian Guo
- API publication date: 2026-08-31; latest retrieved update: 2026-08-31.
- Abstract excerpt: Quantitative trading is moving from isolated predictive models toward agentic workflows that combine reasoning, tool use, memory, and feedback. This survey reviews agentic quantitative trading across five stages: factor mining, signal discovery, portfolio construction, order execution, and risk management. We further examine agentic quant trading systems through architecture, coordination, and adaptation, while comparing benchmarks across strategy construction, offline trading, live market evaluation, and reliability assessment. Our review…

### FaVOR: LLM-Based Agentic Framework for Factor Mining via Empirical Validation

- Source: [2608.30192v1](https://arxiv.org/abs/2608.30192v1)
- Authors: Hyeonjin Kim, Minseok Kim, Seunghyeon Jung, Sujin Pyo, Huisu Jang, Woojin Lee
- API publication date: 2026-08-31; latest retrieved update: 2026-08-31.
- Abstract excerpt: Traditional finance relies on experts to hand-craft factors through a principled process grounded in economic rationale. Recent LLM-based multi-agent systems have automated this process, scaling factor mining far beyond manual effort. However, these automated approaches optimize directly for returns and rarely check whether a generated factor still expresses the economic hypothesis that motivated it. We identify this inconsistency between mathematical form and economic meaning as a structural failure mode of return-oriented automation. The…

### AlphaSeek: Trajectory-Level Self-Iterative Factor Mining Framework for Multi-Source Financial Data

- Source: [2608.13913v1](https://arxiv.org/abs/2608.13913v1)
- Authors: Qilu Zhu, Zijun Lu, Jianmin Zhu, Ning Chen, Shuo Yin, Simon Fong
- API publication date: 2026-08-14; latest retrieved update: 2026-08-14.
- Abstract excerpt: With the rapid rise of large language models, LLM-driven quantitative factor mining has become an increasingly active research area. However, existing methods still suffer from subjective direction design, limited integration of up-to-date multi-source information, semantic drift, factor redundancy, and the absence of an end-to-end feedback loop from factor discovery to portfolio backtesting. To address these limitations, we propose AlphaSeek, an end-to-end factor mining framework for quantitative investment that integrates automated direction…

### AgonAlpha: Autonomous Alpha Discovery via Prompt Economy and Scalable Agentic Search

- Source: [2608.11250v1](https://arxiv.org/abs/2608.11250v1)
- Authors: Weicheng Ye, Youran Sun, Xingyu Ren, Shunyao Yu, Chugang Yi, Haizhao Yang
- API publication date: 2026-08-04; latest retrieved update: 2026-08-04.
- Abstract excerpt: Language models can propose many plausible trading factors, but an autonomous research system must also allocate its evaluation budget, verify its own evidence, and preserve how each candidate was produced. We present AgonAlpha, an architecture that searches over frozen research artifacts---hypotheses, executable expressions, platform evidence, rationales, and review status---rather than formulas alone. To our knowledge, AgonAlpha is the first alpha-mining system to combine verified artifact search, a fresh-context adversarial reviewer with…

### Towards Autonomous Formulaic Alpha Discovery: An Evolutionary Computation Perspective

- Source: [2608.01789v1](https://arxiv.org/abs/2608.01789v1)
- Authors: Xinwei Yu, Yiyang Fu, Mingcheng Fan, Enqi Li, Yilin Gao, Shugong Xu
- API publication date: 2026-08-03; latest retrieved update: 2026-08-03.
- Abstract excerpt: Automated formulaic alpha discovery aims to generate predictive and interpretable trading signals from large symbolic factor spaces. Its effectiveness is constrained by noisy fitness estimates, market nonstationarity, costly backtesting, semantic redundancy, and conflicting practical objectives. Existing studies employ diverse techniques, including genetic programming (GP), evolutionary algorithms (EAs), reinforcement learning (RL), generative flow networks (GFlowNets), Monte Carlo tree search (MCTS), large language models (LLMs), and agentic…

### AlphaSchema: Exploring the Space of Trading Semantics for LLM-Based Alpha Mining

- Source: [2607.26642v1](https://arxiv.org/abs/2607.26642v1)
- Authors: Jingyang Yi, Jian Yang, Yifei Jin, Yuqi Li, Jian Li
- API publication date: 2026-07-29; latest retrieved update: 2026-07-29.
- Abstract excerpt: Automated alpha mining has increasingly adopted large language model (LLM) agents for factor generation and iterative discovery. However, existing LLM-based systems often delegate both factor construction and search decisions to the agent itself, without an explicit exploration space or a principled mechanism for navigating that space. As a result, exploration remains largely implicit and difficult to control or optimize systematically. We introduce AlphaSchema, which constructs and explores a structured space of trading semantics for alpha…

### MAPLE: Efficient and Diverse Multi-Alpha Generation for Portfolio Construction

- Source: [2607.24131v1](https://arxiv.org/abs/2607.24131v1)
- Authors: Yu-Chen Den, Kuan-Yu Chen, Kendro Vincent, Tien-Hao Chang
- API publication date: 2026-07-27; latest retrieved update: 2026-07-27.
- Abstract excerpt: Classical alpha mining achieves strong risk-adjusted returns by combining many low-correlated predictive signals, yet deep learning stock-ranking methods typically produce a single alpha per stock, rely on increasingly complex architectures with diminishing gains, and obtain diversity only through separate models or implicit routing, without explicitly controlling inter-alpha correlation. We introduce MAPLE (Multi-Alpha Position-aware Listwise Ensembling), a backbone-agnostic framework that recovers this diversity principle within a single…

### XALPHA: A Memory-Driven AI Quant Researcher for Hypothesis-to-Code Alpha Discovery

- Source: [2607.08332v2](https://arxiv.org/abs/2607.08332v2)
- Authors: Fengyuan Liu, Yuchen Fu, Yuqi Wang, Qi Liu
- API publication date: 2026-07-09; latest retrieved update: 2026-07-13.
- Abstract excerpt: Financial markets are noisy, non-stationary, and high-dimensional, making it difficult to discover predictive and robust trading signals. Alpha discovery has evolved from manual factor design to machine learning, evolutionary search, and recent LLM-based frameworks, improving the efficiency of factor generation, search, and evaluation. However, existing methods still mostly automate isolated steps, rather than functioning as end-to-end quant researchers that can absorb external knowledge, close the hypothesis-to-code validation loop, and learn…

### Harness-Aware Self-Evolving: Co-Evolving Model Weights, Harness, and Task Solutions

- Source: [2607.03935v1](https://arxiv.org/abs/2607.03935v1)
- Authors: Haochen Luo, Yi Huang, Sichun Luo, Fengyuan Liu, Lei Li, Zefa Hu, Junlan Feng, Qi Liu
- API publication date: 2026-07-04; latest retrieved update: 2026-07-04.
- Abstract excerpt: Self-evolving frameworks usually optimize task solutions while treating the surrounding harness as fixed. We introduce Harness-Aware Self-Evolving (HASE), an agentic reinforcement-learning framework in which a single model can generate task solutions or edit selected harness components in a multi-turn action space. HASE enables a single Qwen3-8B model to match the text-classification performance of a GPT-OSS-120B model that uses Claude Code as the harness proposer. In alpha factor mining, HASE outperforms the reported GPT-OSS-120B baseline.…

### AI Trading's Alpha Singularity: Emergent Market Reasoning through Agent-to-Agent Self-Evolution

- Source: [2606.29194v1](https://arxiv.org/abs/2606.29194v1)
- Authors: Yuqi Li, Siyuan Liu, Bingjun Liu
- API publication date: 2026-06-28; latest retrieved update: 2026-06-28.
- Abstract excerpt: Automated alpha mining holds the scoring function fixed and varies the search algorithm over it. A search that converges against a fixed scorer overfits whatever the scorer cannot penalize, a primary cause of the out-of-sample generalization gap. We treat the scoring function as a search artifact alongside the alpha factors and study what conditions make this joint search admissible. Sealed Joint Search (SJS) is a framework: a set of structural conditions on information flow in an autonomous-discovery system that prevent joint search from…

### AlphaMemo: Structured Search-Process Memory for Self-Evolving Alpha Mining Agents

- Source: [2606.20625v1](https://arxiv.org/abs/2606.20625v1)
- Authors: Hang Yu, Zifan Zheng, Jeff Z. Pan, Tongliang Liu, Zhiyong Wang, Fengxiang He
- API publication date: 2026-05-26; latest retrieved update: 2026-05-26.
- Abstract excerpt: LLM agents are promising for alpha mining via combining financial priors, symbolic reasoning, executable factor generation, and feedback-driven refinement. Yet, they face a combinatorial search space, noisy non-stationary feedback, redundant discoveries, and overfitting risks from naively reusing past successes. To address these challenges, we propose AlphaMemo, a self-evolving alpha mining agent with Structured Search-Process Memory. Rather than memorizing only final factors or full trajectories, AlphaMemo records reusable evidence about…

### FactorEngine: A Program-level Knowledge-Infused Factor Mining Framework for Quantitative Investment

- Source: [2603.16365v3](https://arxiv.org/abs/2603.16365v3)
- Authors: Qinhong Lin, Ruitao Feng, Yinglun Feng, Zhenxin Huang, Yukun Chen, Zhongliang Yang, Linna Zhou, Binjie Fei, Jiaqi Liu, Yu Li
- API publication date: 2026-03-17; latest retrieved update: 2026-09-15.
- Abstract excerpt: We study alpha factor mining, the automated discovery of predictive signals from noisy, non-stationary market data-under a practical requirement that mined factors be directly executable and auditable, and that the discovery process remain computationally tractable at scale. Existing symbolic approaches are limited by bounded expressiveness, while neural forecasters often trade interpretability for performance and remain vulnerable to regime shifts and overfitting. We introduce FactorEngine (FE), a program-level factor discovery framework that…

### AlphaLogics: A Market Logic-Driven Multi-Agent System for Scalable and Interpretable Alpha Factor Generation

- Source: [2603.20247v1](https://arxiv.org/abs/2603.20247v1)
- Authors: Zhangyuhua Weng, Shengli Zhang, Taotao Wang, Yihan Xia
- API publication date: 2026-03-10; latest retrieved update: 2026-03-10.
- Abstract excerpt: Factor investing is ultimately grounded in market logic - the latent mechanism behind observed alpha factors that explains why they should persist across assets and regimes. However, recent factor mining prioritizes factor discovery over logic discovery, producing complex alpha factors with unclear rationale, while market logic remains largely handcrafted and difficult to scale. To address this challenge, we propose AlphaLogics, a market logic-driven multi-agent system for factor mining. AlphaLogics consists of three key components: (i) Market…

### Hubble: An LLM-Driven Agentic Framework for Safe, Diverse, and Reproducible Alpha Factor Discovery

- Source: [2604.09601v2](https://arxiv.org/abs/2604.09601v2)
- Authors: Runze Shi, Shengyu Yan, Yuecheng Cai, Chengxi Lv
- API publication date: 2026-03-09; latest retrieved update: 2026-04-14.
- Abstract excerpt: Automated alpha discovery is difficult because the search space of formulaic factors is combinatorial, the signal-to-noise ratio in daily equity data is low, and unconstrained program generation is operationally unsafe. We present Hubble, an agentic factor mining framework that combines large language models (LLMs) with a domain-specific operator language, an abstract syntax tree (AST) execution sandbox, a dual-channel retrieval-augmented generation (RAG) module, and a family-aware selection mechanism. Instead of treating the LLM as an…

### FactorMiner: A Self-Evolving Agent with Skills and Experience Memory for Financial Alpha Discovery

- Source: [2602.14670v2](https://arxiv.org/abs/2602.14670v2)
- Authors: Yanlong Wang, Jian Xu, Hongkang Zhang, Shao-Lun Huang, Danny Dongning Sun, Xiao-Ping Zhang
- API publication date: 2026-02-16; latest retrieved update: 2026-08-19.
- Abstract excerpt: Formulaic alpha factor mining is a critical yet challenging task in quantitative investment, characterized by a vast search space and the need for domain-informed, interpretable signals. However, finding novel signals becomes increasingly difficult as the library grows due to high redundancy. We propose FactorMiner, a lightweight and flexible self-evolving agent framework designed to navigate this complex landscape through continuous knowledge accumulation. FactorMiner combines a Modular Skill Architecture that encapsulates systematic…

### AlphaPROBE: Alpha Mining via Principled Retrieval and On-graph biased evolution

- Source: [2602.11917v1](https://arxiv.org/abs/2602.11917v1)
- Authors: Taian Guo, Haiyang Shen, Junyu Luo, Binqi Chen, Hongjun Ding, Jinsheng Huang, Luchen Liu, Yun Ma, Ming Zhang
- API publication date: 2026-02-12; latest retrieved update: 2026-02-12.
- Abstract excerpt: Extracting signals through alpha factor mining is a fundamental challenge in quantitative finance. Existing automated methods primarily follow two paradigms: Decoupled Factor Generation, which treats factor discovery as isolated events, and Iterative Factor Evolution, which focuses on local parent-child refinements. However, both paradigms lack a global structural view, often treating factor pools as unstructured collections or fragmented chains, which leads to redundant search and limited diversity. To address these limitations, we introduce…

### QuantaAlpha: An Evolutionary Framework for LLM-Driven Alpha Mining

- Source: [2602.07085v3](https://arxiv.org/abs/2602.07085v3)
- Authors: Jun Han, Shuo Zhang, Wei Li, Yifan Dong, Tu Hu, Yumo Zhu, Xiaomin Yu, Xin Guo, Zhaowei Liu, Kunyi Wang, Jingping Liu, Tianyi Jiang, Ruichuan An, Sen Hu, Zhi Yang, Ronghao Che, Huacan Wang
- API publication date: 2026-02-06; latest retrieved update: 2026-05-18.
- Abstract excerpt: Financial markets are noisy and non-stationary, making alpha mining highly sensitive to backtest noise and regime shifts. While recent agentic frameworks improve automation, they often lack controllable multi-round search and reliable reuse of validated experience. To address these challenges, we propose QuantaAlpha, an evolutionary alpha mining framework that treats each end-to-end mining run as a trajectory and improves factors via trajectory-level mutation and crossover. QuantaAlpha localizes suboptimal steps for targeted revision and…

### Alpha Discovery via Grammar-Guided Learning and Search

- Source: [2601.22119v1](https://arxiv.org/abs/2601.22119v1)
- Authors: Han Yang, Dong Hao, Zhuohan Wang, Qi Shi, Xingtong Li
- API publication date: 2026-01-29; latest retrieved update: 2026-01-29.
- Abstract excerpt: Automatically discovering formulaic alpha factors is a central problem in quantitative finance. Existing methods often ignore syntactic and semantic constraints, relying on exhaustive search over unstructured and unbounded spaces. We present AlphaCFG, a grammar-based framework for defining and discovering alpha factors that are syntactically valid, financially interpretable, and computationally efficient. AlphaCFG uses an alpha-oriented context-free grammar to define a tree-structured, size-controlled search space, and formulates alpha…

### Cognitive Alpha Mining via LLM-Driven Code-Based Evolution

- Source: [2511.18850v4](https://arxiv.org/abs/2511.18850v4)
- Authors: Fengyuan Liu, Yi Huang, Sichun Luo, Yuqi Wang, Yazheng Yang, Xinye Li, Zefa Hu, Junlan Feng, Qi Liu
- API publication date: 2025-11-24; latest retrieved update: 2026-07-11.
- Abstract excerpt: Discovering effective predictive signals, or "alphas," from financial data with high dimensionality and extremely low signal-to-noise ratio remains a difficult open problem. Despite progress in deep learning, genetic programming, and, more recently, large language model (LLM)-based factor generation, existing approaches still explore only a narrow region of the vast alpha search space. Neural models tend to produce opaque and fragile patterns, while symbolic or formula-based methods often yield redundant or economically ungrounded expressions…

### AlphaSAGE: Structure-Aware Alpha Mining via GFlowNets for Robust Exploration

- Source: [2509.25055v3](https://arxiv.org/abs/2509.25055v3)
- Authors: Binqi Chen, Hongjun Ding, Ning Shen, Jinsheng Huang, Taian Guo, Luchen Liu, Ming Zhang
- API publication date: 2025-09-29; latest retrieved update: 2026-05-19.
- Abstract excerpt: The automated mining of predictive signals, or alphas, is a central challenge in quantitative finance. While Reinforcement Learning (RL) has emerged as a promising paradigm for generating formulaic alphas, existing frameworks are fundamentally hampered by a triad of interconnected issues. First, they suffer from reward sparsity, where meaningful feedback is only available upon the completion of a full formula, leading to inefficient and unstable exploration. Second, they rely on semantically inadequate sequential representations of…

### Adaptive Alpha Weighting with PPO: Enhancing Prompt-Based LLM-Generated Alphas in Quant Trading

- Source: [2509.01393v2](https://arxiv.org/abs/2509.01393v2)
- Authors: Qizhao Chen, Hiroaki Kawashima
- API publication date: 2025-09-01; latest retrieved update: 2026-03-04.
- Abstract excerpt: This paper introduces a reinforcement learning framework that employs Proximal Policy Optimization (PPO) to dynamically optimize the weights of multiple large language model (LLM)-generated formulaic alphas for stock trading strategies. Formulaic alphas are mathematically defined trading signals derived from price, volume, sentiment, and other data. Although recent studies have shown that LLMs can generate diverse and effective alphas, a critical challenge lies in how to adaptively integrate them under varying market conditions. To address…

### From Flat to Hierarchical: Evolving Tree-structured Thoughts for Fine-grained Alpha Mining

- Source: [2508.16334v2](https://arxiv.org/abs/2508.16334v2)
- Authors: Junji Ren, Junjie Zhao, Shengcai Liu, Peng Yang
- API publication date: 2025-08-22; latest retrieved update: 2026-05-31.
- Abstract excerpt: Alpha mining, aimed at discovering predictive return signals, is typically formulated as symbolic regression. Traditional symbolic methods suffer from search inefficiency and biased prior knowledge. Recently, Large Language Models (LLMs) have emerged as a promising alternative, automatically generating textual thoughts and executable codes to achieve both efficient and interpretable alpha mining. However, existing approaches mostly focus on leveraging LLM's reasoning and reflection capabilities, yet largely neglect the positional bias due to…

### AlphaEval: A Comprehensive and Efficient Evaluation Framework for Formula Alpha Mining

- Source: [2508.13174v2](https://arxiv.org/abs/2508.13174v2)
- Authors: Hongjun Ding, Binqi Chen, Jinsheng Huang, Taian Guo, Zhengyang Mao, Guoyi Shao, Lutong Zou, Luchen Liu, Ming Zhang
- API publication date: 2025-08-10; latest retrieved update: 2026-06-02.
- Abstract excerpt: Formula alpha mining, which generates predictive signals from financial data, is critical for quantitative investment. Although various algorithmic approaches-such as genetic programming, reinforcement learning, and large language models-have significantly expanded the capacity for alpha discovery, systematic evaluation remains a key challenge. Existing evaluation metrics predominantly include backtesting and correlation-based measures. Backtesting is computationally intensive, inherently sequential, and sensitive to specific strategy…

### Chain-of-Alpha: Unleashing the Power of Large Language Models for Alpha Mining in Quantitative Trading

- Source: [2508.06312v2](https://arxiv.org/abs/2508.06312v2)
- Authors: Lang Cao
- API publication date: 2025-08-08; latest retrieved update: 2025-08-28.
- Abstract excerpt: Alpha factor mining is a fundamental task in quantitative trading, aimed at discovering interpretable signals that can predict asset returns beyond systematic market risk. While traditional methods rely on manual formula design or heuristic search with machine learning, recent advances have leveraged Large Language Models (LLMs) for automated factor discovery. However, existing LLM-based alpha mining approaches remain limited in terms of automation, generality, and efficiency. In this paper, we propose Chain-of-Alpha, a novel, simple, yet…

### Sentiment-Aware Stock Price Prediction with Transformer and LLM-Generated Formulaic Alpha

- Source: [2508.04975v2](https://arxiv.org/abs/2508.04975v2)
- Authors: Qizhao Chen, Hiroaki Kawashima
- API publication date: 2025-08-07; latest retrieved update: 2026-03-04.
- Abstract excerpt: Traditionally, traders and quantitative analysts address alpha decay by manually crafting formulaic alphas, mathematical expressions that identify patterns or signals in financial data, through domain expertise and trial-and-error. This process is often time-consuming and difficult to scale. With recent advances in large language models (LLMs), it is now possible to automate the generation of such alphas by leveraging the reasoning capabilities of LLMs. This paper introduces a novel framework that integrates a prompt-based LLM with a…

### Learning from Expert Factors: Trajectory-level Reward Shaping for Formulaic Alpha Mining

- Source: [2507.20263v1](https://arxiv.org/abs/2507.20263v1)
- Authors: Junjie Zhao, Chengxi Zhang, Chenkai Wang, Peng Yang
- API publication date: 2025-07-27; latest retrieved update: 2025-07-27.
- Abstract excerpt: Reinforcement learning (RL) has successfully automated the complex process of mining formulaic alpha factors, for creating interpretable and profitable investment strategies. However, existing methods are hampered by the sparse rewards given the underlying Markov Decision Process. This inefficiency limits the exploration of the vast symbolic search space and destabilizes the training process. To address this, Trajectory-level Reward Shaping (TLRS), a novel reward shaping method, is proposed. TLRS provides dense, intermediate rewards by…

### R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and Model Joint Optimization

- Source: [2505.15155v2](https://arxiv.org/abs/2505.15155v2)
- Authors: Yuante Li, Xu Yang, Xiao Yang, Minrui Xu, Xisen Wang, Weiqing Liu, Jiang Bian
- API publication date: 2025-05-21; latest retrieved update: 2025-09-25.
- Abstract excerpt: Financial markets pose fundamental challenges for asset return prediction due to their high dimensionality, non-stationarity, and persistent volatility. Despite advances in large language models and multi-agent systems, current quantitative research pipelines suffer from limited automation, weak interpretability, and fragmented coordination across key components such as factor mining and model innovation. In this paper, we propose R&D-Agent for Quantitative Finance, in short RD-Agent(Q), the first data-centric multi-agent framework designed to…

### Navigating the Alpha Jungle: An LLM-Powered MCTS Framework for Formulaic Factor Mining

- Source: [2505.11122v3](https://arxiv.org/abs/2505.11122v3)
- Authors: Yu Shi, Yitong Duan, Jian Li
- API publication date: 2025-05-16; latest retrieved update: 2025-11-12.
- Abstract excerpt: Alpha factor mining is pivotal in quantitative investment for identifying predictive signals from complex financial data. While traditional formulaic alpha mining relies on human expertise, contemporary automated methods, such as those based on genetic programming or reinforcement learning, often struggle with search inefficiency or yield alpha factors that are difficult to interpret. This paper introduces a novel framework that integrates Large Language Models (LLMs) with Monte Carlo Tree Search (MCTS) to overcome these limitations. Our…

### AlphaAgent: LLM-Driven Alpha Mining with Regularized Exploration to Counteract Alpha Decay

- Source: [2502.16789v2](https://arxiv.org/abs/2502.16789v2)
- Authors: Ziyi Tang, Zechuan Chen, Jiarui Yang, Jiayao Mai, Yongsen Zheng, Keze Wang, Jinrui Chen, Liang Lin
- API publication date: 2025-02-24; latest retrieved update: 2025-06-09.
- Abstract excerpt: Alpha mining, a critical component in quantitative investment, focuses on discovering predictive signals for future asset returns in increasingly complex financial markets. However, the pervasive issue of alpha decay, where factors lose their predictive power over time, poses a significant challenge for alpha mining. Traditional methods like genetic programming face rapid alpha decay from overfitting and complexity, while approaches driven by Large Language Models (LLMs), despite their promise, often rely too heavily on existing knowledge,…

### Alpha Mining and Enhancing via Warm Start Genetic Programming for Quantitative Investment

- Source: [2412.00896v1](https://arxiv.org/abs/2412.00896v1)
- Authors: Weizhe Ren, Yichen Qin, Yang Li
- API publication date: 2024-12-01; latest retrieved update: 2024-12-01.
- Abstract excerpt: Traditional genetic programming (GP) often struggles in stock alpha factor discovery due to its vast search space, overwhelming computational burden, and sporadic effective alphas. We find that GP performs better when focusing on promising regions rather than random searching. This paper proposes a new GP framework with carefully chosen initialization and structural constraints to enhance search performance and improve the interpretability of the alpha factors. This approach is motivated by and mimics the alpha searching practice and aims to…

### Alphanetv4: Alpha Mining Model

- Source: [2411.04409v1](https://arxiv.org/abs/2411.04409v1)
- Authors: Wenjun Wu
- API publication date: 2024-11-07; latest retrieved update: 2024-11-07.
- Abstract excerpt: As AI and deep learning have become hot spots in the 21st century , they are widely used in the current quant market. In 2020, Huatai Securities constructed deep-learning-based AlphaNet for stock feature extraction and price prediction. At present, it has developed to the 3rd version and has formed a great influence in the market. However, the AlphaNet has some problems, such as underfitting caused by short sequence length of feature extraction, insufficient diversity of feature extraction, high complexity, instability of random sampling,…

### GPT-Signal: Generative AI for Semi-automated Feature Engineering in the Alpha Research Process

- Source: [2410.18448v1](https://arxiv.org/abs/2410.18448v1)
- Authors: Yining Wang, Jinman Zhao, Yuri Lawryshyn
- API publication date: 2024-10-24; latest retrieved update: 2024-10-24.
- Abstract excerpt: In the trading process, financial signals often imply the time to buy and sell assets to generate excess returns compared to a benchmark (e.g., an index). Alpha is the portion of an asset's return that is not explained by exposure to this benchmark, and the alpha research process is a popular technique aiming at developing strategies to generate alphas and gain excess returns. Feature Engineering, a significant pre-processing procedure in machine learning and data analysis that helps extract and create transformed features from raw data, plays…

### QuantFactor REINFORCE: Mining Steady Formulaic Alpha Factors with Variance-bounded REINFORCE

- Source: [2409.05144v3](https://arxiv.org/abs/2409.05144v3)
- Authors: Junjie Zhao, Chengxi Zhang, Min Qin, Peng Yang
- API publication date: 2024-09-08; latest retrieved update: 2025-06-17.
- Abstract excerpt: Alpha factor mining aims to discover investment signals from the historical financial market data, which can be used to predict asset returns and gain excess profits. Powerful deep learning methods for alpha factor mining lack interpretability, making them unacceptable in the risk-sensitive real markets. Formulaic alpha factors are preferred for their interpretability, while the search space is complex and powerful explorative methods are urged. Recently, a promising framework is proposed for generating formulaic alpha factors using deep…

### HRFT: Mining High-Frequency Risk Factor Collections End-to-End via Transformer

- Source: [2408.01271v5](https://arxiv.org/abs/2408.01271v5)
- Authors: Wenyan Xu, Rundong Wang, Chen Li, Yonghong Hu, Zhonghua Lu
- API publication date: 2024-08-02; latest retrieved update: 2025-09-20.
- Abstract excerpt: In quantitative trading, transforming historical stock data into interpretable, formulaic risk factors enhances the identification of market volatility and risk. Despite recent advancements in neural networks for extracting latent risk factors, these models remain limited to feature extraction and lack explicit, formulaic risk factor designs. By viewing symbolic mathematics as a language where valid mathematical expressions serve as meaningful "sentences" we propose framing the task of mining formulaic risk factors as a language modeling…

### AlphaForge: A Framework to Mine and Dynamically Combine Formulaic Alpha Factors

- Source: [2406.18394v5](https://arxiv.org/abs/2406.18394v5)
- Authors: Hao Shi, Weili Song, Xinting Zhang, Jiahe Shi, Cuicui Luo, Xiang Ao, Hamid Arian, Luis Seco
- API publication date: 2024-06-26; latest retrieved update: 2024-12-12.
- Abstract excerpt: The complexity of financial data, characterized by its variability and low signal-to-noise ratio, necessitates advanced methods in quantitative investment that prioritize both performance and interpretability.Transitioning from early manual extraction to genetic programming, the most advanced approach in the alpha factor mining domain currently employs reinforcement learning to mine a set of combination factors with fixed weights. However, the performance of resultant alpha factors exhibits inconsistency, and the inflexibility of fixed factor…

### Alpha²: Discovering Logical Formulaic Alphas using Deep Reinforcement Learning

- Source: [2406.16505v2](https://arxiv.org/abs/2406.16505v2)
- Authors: Feng Xu, Yan Yin, Xinyu Zhang, Tianyuan Liu, Shengyi Jiang, Zongzhang Zhang
- API publication date: 2024-06-24; latest retrieved update: 2024-06-26.
- Abstract excerpt: Alphas are pivotal in providing signals for quantitative trading. The industry highly values the discovery of formulaic alphas for their interpretability and ease of analysis, compared with the expressive yet overfitting-prone black-box alphas. In this work, we focus on discovering formulaic alphas. Prior studies on automatically generating a collection of formulaic alphas were mostly based on genetic programming (GP), which is known to suffer from the problems of being sensitive to the initial population, converting to local optima, and slow…

### Alpha-GPT 2.0: Human-in-the-Loop AI for Quantitative Investment

- Source: [2402.09746v1](https://arxiv.org/abs/2402.09746v1)
- Authors: Hang Yuan, Saizhuo Wang, Jian Guo
- API publication date: 2024-02-15; latest retrieved update: 2024-02-15.
- Abstract excerpt: Recently, we introduced a new paradigm for alpha mining in the realm of quantitative investment, developing a new interactive alpha mining system framework, Alpha-GPT. This system is centered on iterative Human-AI interaction based on large language models, introducing a Human-in-the-Loop approach to alpha discovery. In this paper, we present the next-generation Alpha-GPT 2.0 \footnote{Draft. Work in progress}, a quantitative investment framework that further encompasses crucial modeling and analysis phases in quantitative investment. This…

### RiskMiner: Discovering Formulaic Alphas via Risk Seeking Monte Carlo Tree Search

- Source: [2402.07080v2](https://arxiv.org/abs/2402.07080v2)
- Authors: Tao Ren, Ruihan Zhou, Jinyang Jiang, Jiafeng Liang, Qinghao Wang, Yijie Peng
- API publication date: 2024-02-11; latest retrieved update: 2024-02-29.
- Abstract excerpt: The formulaic alphas are mathematical formulas that transform raw stock data into indicated signals. In the industry, a collection of formulaic alphas is combined to enhance modeling accuracy. Existing alpha mining only employs the neural network agent, unable to utilize the structural information of the solution space. Moreover, they didn't consider the correlation between alphas in the collection, which limits the synergistic performance. To address these problems, we propose a novel alpha mining framework, which formulates the alpha mining…

### Synergistic Formulaic Alpha Generation for Quantitative Trading based on Reinforcement Learning

- Source: [2401.02710v2](https://arxiv.org/abs/2401.02710v2)
- Authors: Hong-Gi Shin, Sukhyun Jeong, Eui-Yeon Kim, Sungho Hong, Young-Jin Cho, Yong-Hoon Choi
- API publication date: 2024-01-05; latest retrieved update: 2024-07-08.
- Abstract excerpt: Mining of formulaic alpha factors refers to the process of discovering and developing specific factors or indicators (referred to as alpha factors) for quantitative trading in stock market. To efficiently discover alpha factors in vast search space, reinforcement learning (RL) is commonly employed. This paper proposes a method to enhance existing alpha factor mining approaches by expanding a search space and utilizing pretrained formulaic alpha set as initial seed values to generate synergistic formulaic alpha. We employ information…

### Microstructure-Empowered Stock Factor Extraction and Utilization

- Source: [2308.08135v1](https://arxiv.org/abs/2308.08135v1)
- Authors: Xianfeng Jiao, Zizhong Li, Chang Xu, Yang Liu, Weiqing Liu, Jiang Bian
- API publication date: 2023-08-16; latest retrieved update: 2023-08-16.
- Abstract excerpt: High-frequency quantitative investment is a crucial aspect of stock investment. Notably, order flow data plays a critical role as it provides the most detailed level of information among high-frequency trading data, including comprehensive data from the order book and transaction records at the tick level. The order flow data is extremely valuable for market analysis as it equips traders with essential insights for making informed decisions. However, extracting and effectively utilizing order flow data present challenges due to the large…

### Alpha-GPT: Human-AI Interactive Alpha Mining for Quantitative Investment

- Source: [2308.00016v2](https://arxiv.org/abs/2308.00016v2)
- Authors: Saizhuo Wang, Hang Yuan, Leon Zhou, Lionel M. Ni, Heung-Yeung Shum, Jian Guo
- API publication date: 2023-07-31; latest retrieved update: 2025-09-20.
- Abstract excerpt: One of the most important tasks in quantitative investment research is mining new alphas (effective trading signals or factors). Traditional alpha mining methods, either hand-crafted factor synthesizing or algorithmic factor mining (e.g., search with genetic programming), have inherent limitations, especially in implementing the ideas of quants. In this work, we propose a new alpha mining paradigm by introducing human-AI interaction, and a novel prompt engineering algorithmic framework to implement this paradigm by leveraging the power of…

### Generating Synergistic Formulaic Alpha Collections via Reinforcement Learning

- Source: [2306.12964v1](https://arxiv.org/abs/2306.12964v1)
- Authors: Shuo Yu, Hongyan Xue, Xiang Ao, Feiyang Pan, Jia He, Dandan Tu, Qing He
- API publication date: 2023-05-25; latest retrieved update: 2023-05-25.
- Abstract excerpt: In the field of quantitative trading, it is common practice to transform raw historical stock data into indicative signals for the market trend. Such signals are called alpha factors. Alphas in formula forms are more interpretable and thus favored by practitioners concerned with risk. In practice, a set of formulaic alphas is often used together for better modeling precision, so we need to find synergistic formulaic alpha sets that work well together. However, most traditional alpha generators mine alphas one by one separately, overlooking the…

### AlphaEvolve: A Learning Framework to Discover Novel Alphas in Quantitative Investment

- Source: [2103.16196v2](https://arxiv.org/abs/2103.16196v2)
- Authors: Can Cui, Wei Wang, Meihui Zhang, Gang Chen, Zhaojing Luo, Beng Chin Ooi
- API publication date: 2021-03-30; latest retrieved update: 2021-04-01.
- Abstract excerpt: Alphas are stock prediction models capturing trading signals in a stock market. A set of effective alphas can generate weakly correlated high returns to diversify the risk. Existing alphas can be categorized into two classes: Formulaic alphas are simple algebraic expressions of scalar features, and thus can generalize well and be mined into a weakly correlated set. Machine learning alphas are data-driven models over vector and matrix features. They are more predictive than formulaic alphas, but are too complex to mine into a weakly correlated…

### AutoAlpha: an Efficient Hierarchical Evolutionary Algorithm for Mining Alpha Factors in Quantitative Investment

- Source: [2002.08245v2](https://arxiv.org/abs/2002.08245v2)
- Authors: Tianping Zhang, Yuanqi Li, Yifei Jin, Jian Li
- API publication date: 2020-02-09; latest retrieved update: 2020-04-04.
- Abstract excerpt: The multi-factor model is a widely used model in quantitative investment. The success of a multi-factor model is largely determined by the effectiveness of the alpha factors used in the model. This paper proposes a new evolutionary algorithm called AutoAlpha to automatically generate effective formulaic alphas from massive stock datasets. Specifically, first we discover an inherent pattern of the formulaic alphas and propose a hierarchical structure to quickly locate the promising part of space for search. Then we propose a new Quality…

### 101 Formulaic Alphas

- Source: [1601.00991v3](https://arxiv.org/abs/1601.00991v3)
- Authors: Zura Kakushadze
- API publication date: 2016-01-05; latest retrieved update: 2016-03-18.
- Abstract excerpt: We present explicit formulas - that are also computer code - for 101 real-life quantitative trading alphas. Their average holding period approximately ranges 0.6-6.4 days. The average pair-wise correlation of these alphas is low, 15.9%. The returns are strongly correlated with volatility, but have no significant dependence on turnover, directly confirming an earlier result based on a more indirect empirical analysis. We further find empirically that turnover has poor explanatory power for alpha correlations.

## Additional targeted gradient references

- [Differentiable Genetic Programming](https://arxiv.org/abs/1611.04766v1): primary abstract checked; high-order automatic differentiation in Cartesian genetic programming.
- [Differentiable Genetic Programming for High-dimensional Symbolic Regression](https://arxiv.org/abs/2304.08915v1): abstract and selected PDF method sections checked; differentiable symbolic trees, structure relaxation, sampling, and diversification.
- [AlphaQCM — ICML 2025 proceedings](https://proceedings.mlr.press/v267/zhu25ag.html): official proceedings entry verifies title, authors, venue, paper link, and author repository.
