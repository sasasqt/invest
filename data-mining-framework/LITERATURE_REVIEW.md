# Industry-oriented factor mining: literature and implementation roadmap

Research date: October 5, 2026. Scope: financial alpha and feature mining, especially interpretable formulas, expression trees, gradient-assisted search, and exploration versus exploitation.

## Main recommendation

Build a common typed expression engine, a reproducible evaluator, and a diverse factor archive before implementing a sophisticated search algorithm. Start with random search and genetic programming, then compare an AlphaGen-style pool-aware search against a FEAT-style hybrid of tree evolution and numeric optimization. Add uncertainty-aware or GFlowNet search only after those baselines work under the same evaluation budget.

For the closest connections to applied quant research, prioritize AlphaGen, AlphaForge, AlphaQCM, AlphaEval, Qlib, and R&D-Agent-Quant. For backpropagation through symbolic features or relaxed tree structure, prioritize FEAT, Differentiable Genetic Programming, DGP for high-dimensional symbolic regression, and AlphaForge's surrogate-guided generation. For exploration and diverse factor collections, prioritize RiskMiner, AlphaCFG, AlphaSAGE, AlphaPROBE, GFlowNets, and neural-guided genetic programming.

## Search and evidence limits

Initial research used GitHub repository search and author/project repositories because scholarly hosts were blocked. After the environment restart, Google, Bing, arXiv, the arXiv API, and OpenAlex returned HTTP 200. Google's response was a redirect/interstitial and the initial Bing results were irrelevant, so the substantive expansion used arXiv and OpenAlex search, proceedings metadata, and selected paper PDFs. This is a broad research map, not an exhaustive systematic review or a full-text review of every paper.

The broad arXiv query returned 54 records; 49 were retained as relevant or adjacent financial research after excluding unrelated word matches and one generic decision-making paper. See the [primary-source catalog](PRIMARY_SOURCE_CATALOG.md) for titles, authors, version links, and abstract excerpts. Additional targeted searches covered differentiable genetic programming and AlphaQCM. Recent preprints are discovery leads, not established industry practice.

Evidence labels used below:

- **F — selected full-text checked:** PDF retrieved and relevant method, evaluation, or limitations sections inspected; this does not mean every claim or proof was audited.
- **A — primary abstract checked:** title and abstract retrieved from arXiv or a proceedings page, without a full method review.
- **P — project verified:** title or method checked against an author/project repository or its documentation. Linked paper pages were not necessarily accessible.
- **S — secondary verified:** checked against a benchmark or reproduction repository; original bibliographic details still need confirmation.
- **B — background reference:** established methodological or finance reference included for completeness; its primary page was not inspected in this session.

Descriptions of implementation choices are recommendations, not claims that a cited paper implemented them. No experiments, reported returns, or live trading results were independently reproduced. Open code, realistic historical data, or industry affiliation is useful evidence of applicability, but does not establish production deployment or net profitability. Dates and venues are included only where supported by inspected documentation, primary metadata, or explicitly labeled as background. Latest retrieved paper versions were used for the follow-up; evidence levels for the original entries remain as stated unless upgraded below.

## What “factor” means here

A formulaic alpha maps information available at a decision time to a signal for each instrument. A latent risk factor, a return predictor, and an executable trading strategy are related but distinct outputs. Symbolic-regression papers often minimize prediction error; financial alpha mining often optimizes cross-sectional information coefficient (IC), rank IC, or the marginal contribution to a factor collection. None of those scores alone establishes a tradable strategy.

The same engine can support daily market data, fundamentals, or alternative data, but timing, units, legal access, and missing-data behavior must be explicit. Initially target daily cross-sectional equities, which aligns with several accessible reference implementations. Intraday and other markets require separate execution assumptions and validation.

## 1. Direct financial alpha mining

| Work | Evidence and source | Main idea | Why it matters here | Important limitation |
|---|---|---|---|---|
| **Generating Synergistic Formulaic Alpha Collections via Reinforcement Learning — AlphaGen** (Yu et al., KDD 2023, Applied Data Science track) | **P**: [author repository](https://github.com/RL-MLDM/alphagen); [paper DOI](https://doi.org/10.1145/3580305.3599831) | Generate formulas with reinforcement learning and evaluate their contribution to an alpha collection. | Strong starting point for a grammar-constrained search policy, evaluator interface, and pool-aware selection. The documented calculator abstraction supports replacing the data backend. | Neural policy training is not differentiation through discrete formula structure. Historical performance requires independent cost and leakage checks. |
| **AlphaForge: A Framework to Mine and Dynamically Combine Formulaic Alpha Factors** (AAAI 2025) | **F**: [paper](https://arxiv.org/abs/2406.18394); [author repository](https://github.com/DulyHao/AlphaForge) | Generative-predictive factor mining using a differentiable fitness surrogate, Gumbel-Softmax, diversity losses, and subsequent adaptive combination. | Adopt separate candidate generation, factor archive, and combination stages. The README documents chronological train/validation/test periods and a separate combination command. | Adaptive combination must use only information available before the next trade. Section “Simulated Trading and Real Money Investment” reports a real account; this remains an author claim, not an independently audited result. Surrogate exploitation and relaxation mismatch require testing. |
| **AlphaQCM: Alpha Discovery in Finance with Distributional Reinforcement Learning** (Zhoufan Zhu and Ke Zhu, ICML 2025) | **A/P**: [proceedings](https://proceedings.mlr.press/v267/zhu25ag.html); [author repository](https://github.com/ZhuZhouFan/AlphaQCM); [training implementation](https://github.com/ZhuZhouFan/AlphaQCM/blob/main/train_qcm.py) | Apply distributional RL to the alpha-discovery environment, with quantile-based agents and an uncertainty-related tuning parameter. | Relevant to exploration guided by richer action-value estimates rather than only expected reward. The implementation exposes QRDQN/IQN choices and factor-pool output. | A return distribution models more than epistemic uncertainty; its spread is not automatically a reliable confidence interval. The ICML proceedings now establish the venue and official code link; the full method still needs a dedicated review. |
| **AlphaSAGE: Structure-Aware Alpha Mining via GFlowNets for Robust Exploration** (2025 preprint; retrieved PDF identifies ICLR 2026 publication) | **F**: [author repository](https://github.com/BerkinChen/AlphaSAGE); [paper](https://arxiv.org/abs/2509.25055) | Structure-aware graph encoding, GFlowNet generation, and multifaceted feedback for diverse expressions. | Closely matches AST-aware representations and the need to generate several useful, different alphas. The README documents novelty and entropy controls. | Inspect how rewards are defined and made positive, and how intermediate rewards affect the target distribution. Repository superiority claims were not independently checked. |
| **AlphaPROBE: Alpha Mining via Principled Retrieval and On-graph Biased Evolution** (2026 preprint) | **P**: [author repository](https://github.com/gta0804/AlphaPROBE); [paper](https://arxiv.org/abs/2602.11917) | Bayesian factor retrieval and DAG-aware generation/evolution in a closed loop. | A direct reference for selecting which existing factors to improve and tracking relationships among derived factors. Listed affiliations include Zhengren Quant, giving a concrete industry connection. | Affiliation does not establish live deployment. Requires scrutiny of retrieval uncertainty, validation reuse, LLM costs, and reproducibility. |
| **A hybrid approach to formulaic alpha discovery with large language model assistance — HARLA** (Frontiers of Computer Science, 2026 citation in repository) | **P**: [author repository and citation](https://github.com/RL-MLDM/alphagen); [paper DOI](https://doi.org/10.1007/S11704-025-41061-5) | Combine conventional alpha discovery with LLM assistance. | Use language models to supply hypotheses or useful starting expressions while keeping numerical evaluation independent. | LLM-generated explanations are not evidence that a factor works. Model versions and generated expressions must be saved. |
| **R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and Model Joint Optimization** (2025; NeurIPS acceptance reported by project) | **P**: [Microsoft project](https://github.com/microsoft/RD-Agent); [paper](https://arxiv.org/abs/2505.15155) | Iterative factor and downstream-model co-optimization with research and development agents. | Relevant to the full research loop: hypothesis, implementation, execution, feedback, and experiment management. | Joint optimization expands the search space and the number of trials; model selection must be nested inside evaluation. Project-reported returns and dollar costs are not reproduced here. |
| **AutoAlpha: an Efficient Hierarchical Evolutionary Algorithm for Mining Alpha Factors in Quantitative Investment** (2020) | **A/S**: [educational reproduction](https://github.com/bigsuperFishfish/AutoAlpha); [primary abstract now verified](https://arxiv.org/abs/2002.08245); [AlphaEval comparison repository](https://github.com/LeoDingggg/AlphaEval) | Hierarchical evolutionary search with reusable building blocks and diversity-oriented search. | Useful non-neural baseline and motivation for search by complexity/depth and an archive of useful subexpressions. | The inspected implementation explicitly identifies itself as educational; its detailed claims and numeric results must not be treated as an audited reproduction of the original paper. |
| **Mining Profitable Alpha Factors via Convolution Kernel Learning** (OpenAlex records 2023 publication) | **P/S**, limited: [indexed DOI](https://doi.org/10.1007/s10489-023-05014-4); [repository identifying itself as the paper's source](https://github.com/szy1900/autoAlpha) | Learning-based alpha extraction through convolution kernels. | Additional route to investigate for gradient-based feature mining rather than only discrete tree search. | Publication metadata was found via OpenAlex, but neither the brief README nor indexing establishes detailed architecture or equivalence to differentiating an AST. This is a follow-up lead, not a basis for implementation claims. |
| **AlphaEval: A Comprehensive and Efficient Evaluation Framework for Formula Alpha Mining** (2025 preprint; v2 updated in 2026) | **F**: [project repository](https://github.com/LeoDingggg/AlphaEval); [paper](https://arxiv.org/abs/2508.13174) | A parallelizable, backtest-free factor evaluation framework spanning predictive power, stability, perturbation robustness, financial logic, and diversity. | Essential comparison reference: compare miners through the same evaluator and dataset, not separately tuned backtests. | Included implementations differ in provenance. Its Section 7 explicitly states that it evaluates factors, not complete trading strategies; logic scoring depends on LLM judgments. Retain an execution-aware backtest. Do not confuse this with the unrelated GAIR-NLP project also named AlphaEval. |

### Follow-up: AST search and exploration papers now verified

| Paper | Evidence | Mechanism and implementation relevance | Review concern |
|---|---|---|---|
| **AlphaEvolve: A Learning Framework to Discover Novel Alphas in Quantitative Investment** (Cui et al., 2021) | **A**: [paper](https://arxiv.org/abs/2103.16196) | Evolve alpha programs over scalar, vector, and matrix features; inject relational stock knowledge and prune redundant alphas. Broader representation than scalar-only formulas. | Relational inputs require point-in-time membership and leakage-safe graph construction. This is separate from Google's similarly named AlphaEvolve system. |
| **RiskMiner: Discovering Formulaic Alphas via Risk Seeking Monte Carlo Tree Search** (Ren et al., 2024 preprint) | **F**: [paper](https://arxiv.org/abs/2402.07080) | Dense feedback for valid partial expressions, pool redundancy penalties, and risk-seeking MCTS. Direct finance reference for exploration/exploitation over formula construction. | “Risk-seeking” concerns search rewards, not permission to take more portfolio risk. Noisy upper-tail rewards can favor lucky candidates. |
| **Alpha²: Discovering Logical Formulaic Alphas using Deep Reinforcement Learning** (Xu et al., 2024 preprint) | **A**: [paper](https://arxiv.org/abs/2406.16505); [code linked by abstract](https://github.com/x35f/alpha2) | Program construction with guided search, performance/diversity objectives, and pre-calculation dimensional analysis. Particularly relevant to typed/unit-aware ASTs. | Unit rules prune nonsensical expressions but do not prove economic validity or predictive value. |
| **AlphaAgent: LLM-Driven Alpha Mining with Regularized Exploration to Counteract Alpha Decay** (Tang et al., 2025) | **F**: [paper](https://arxiv.org/abs/2502.16789); [indexed publication DOI](https://doi.org/10.1145/3711896.3736838) | AST similarity against existing factors, hypothesis-factor alignment, and AST complexity constraints. Direct match to originality and regularized exploration. | Structural novelty can coexist with economically redundant signals; LLM semantic scoring is model-dependent. |
| **Navigating the Alpha Jungle: An LLM-Powered MCTS Framework for Formulaic Factor Mining** (Shi, Duan, Li, 2025 preprint; OpenAlex indexes AAAI 2026 version) | **A**: [paper](https://arxiv.org/abs/2505.11122); [indexed proceedings DOI](https://doi.org/10.1609/aaai.v40i2.37069) | MCTS-guided LLM proposals and frequent-subtree avoidance. A finance-specific alternative to generic UCT references. | Measure branching cost, subtree redundancy, and improvements under matched evaluation/token budgets. |
| **Learning from Expert Factors: Trajectory-level Reward Shaping for Formulaic Alpha Mining** (2025 preprint) | **A**: [paper](https://arxiv.org/abs/2507.20263) | Dense rewards from subsequence similarity to expert formulas, plus reward centering. | Expert shaping may improve efficiency while restricting novelty; verify whether shaping changes the intended objective. |
| **QuantFactor REINFORCE: Mining Steady Formulaic Alpha Factors with Variance-bounded REINFORCE** (2024 preprint; API records IEEE Transactions on Signal Processing, 2025) | **A**: [paper](https://arxiv.org/abs/2409.05144) | Dedicated REINFORCE baseline and stability-oriented shaping; challenges the default choice of PPO for largely deterministic construction transitions. | Lower estimator variance does not eliminate noisy financial reward estimates or selection bias. |
| **Alpha Discovery via Grammar-Guided Learning and Search — AlphaCFG** (Yang et al., 2026 preprint) | **F**: [paper](https://arxiv.org/abs/2601.22119) | Context-free alpha grammar, size-controlled trees, Tree-LSTM value representation, and grammar-aware policy/value-guided MCTS. | Tree-search “backpropagation” updates visit/value statistics; it is not a derivative through operators. Learned value estimates need out-of-sample calibration. |
| **FactorEngine: A Program-level Knowledge-Infused Factor Mining Framework for Quantitative Investment** (Lin et al., 2026 preprint) | **F**: [paper](https://arxiv.org/abs/2603.16365) | Separate logic revisions from local parameter search; UCT over program lineage, TPE-supported parameter optimization, report-derived seeds, and multi-island evolution. | Program-level execution is broader than an AST DSL. The paper acknowledges modern LLM training data may extend beyond historical evaluation periods. |
| **HRFT: Mining High-Frequency Risk Factor Collections End-to-End via Transformer** (2024 preprint; abstract calls the method IRFT) | **A**: [paper](https://arxiv.org/abs/2408.01271) | Transformer predicts symbolic/numeric tokens and refines constants with BFGS. Bridges expression generation and continuous fitting for high-frequency risk factors. | Risk factors and predictive alphas are different objectives. Confirm the HRFT/IRFT naming and exact execution assumptions in full text. |
| **Microstructure-Empowered Stock Factor Extraction and Utilization** (2023) | **A**: [paper](https://arxiv.org/abs/2308.08135) | Context encoder and unsupervised extraction from order flow for prediction and execution tasks. | Adjacent learned-factor research, not explicit AST mining. Tick-data throughput and market microstructure require a separate data contract. |

### Recent extensions: primary abstracts checked, experiments not reproduced

These 2026 works broaden the search map. Start with established baselines rather than treating every new preprint as a required dependency.

| Paper | Source | Useful idea |
|---|---|---|
| **AlphaPROBE** | [paper](https://arxiv.org/abs/2602.11917) | Bayesian parent retrieval and global evolutionary DAG; primary abstract confirms exploration/exploitation framing. |
| **FactorMiner: A Self-Evolving Agent with Skills and Experience Memory for Financial Alpha Discovery** | [paper](https://arxiv.org/abs/2602.14670) | Reusable evaluation tools and experience memory to reduce redundant discovery. |
| **QuantaAlpha: An Evolutionary Framework for LLM-Driven Alpha Mining** | [paper](https://arxiv.org/abs/2602.07085) | Mutate and recombine complete research trajectories, with consistency checks. |
| **AlphaMemo: Structured Search-Process Memory for Self-Evolving Alpha Mining Agents** | [paper](https://arxiv.org/abs/2606.20625) | Store AST-diff edit motifs and confidence-gated success/failure evidence. Particularly relevant to reusable tree edits. |
| **AlphaSchema: Exploring the Space of Trading Semantics for LLM-Based Alpha Mining** | [paper](https://arxiv.org/abs/2607.26642) | Explicit semantic search space and surrogate-guided exploration/exploitation, separated from LLM implementation. |
| **AgonAlpha: Autonomous Alpha Discovery via Prompt Economy and Scalable Agentic Search** | [paper](https://arxiv.org/abs/2608.11250) | Frozen research artifacts, independent adversarial review, parallel budget allocation, and author-reported WorldQuant BRAIN deployment. Platform grades are not audited live P&L. |
| **FaVOR: LLM-Based Agentic Framework for Factor Mining via Empirical Validation** | [paper](https://arxiv.org/abs/2608.30192) | Decompose economic hypotheses into observable conditions and verify meaning before integration. |
| **AlphaRJM: Reward-Jump Memory for Stochastic Return-Guided Alpha Discovery** | [paper](https://arxiv.org/abs/2609.08581) | Terminal-event memory and a stochastic distributional return critic for uncertain construction choices. |
| **AlphaPareto: Formulaic Alpha Discovery with LLM-Guided Multi-Objective Reinforcement Learning** | [paper](https://arxiv.org/abs/2609.34188) | Make pool state explicit and optimize vector-valued objectives under evolving search rewards. |
| **AlphaDiverse: Post-Training Local Quantitative Research Agents for Diverse Exploration in Alpha Factor Mining** | [paper](https://arxiv.org/abs/2609.29014) | Train local agents for varied research paths; abstract explicitly separates inner feedback and frozen outer evaluation. |
| **From Search to Research: Exploring Search Scaling in Autonomous Quantitative Factor Mining** | [paper](https://arxiv.org/abs/2609.35559) | Compare model strength, search depth, and parallel versus sequential organization on report-grounded tasks. |

Other retrieved leads, including Alpha-GPT, Alpha-GPT 2.0, TreEvo, Chain-of-Alpha, CogAlpha, AlphaSeek, XAlpha, AlphaLogics, MAPLE, warm-start GP, and surveys, are listed in the catalog. They provide alternatives for human interaction, thought/trajectory evolution, learned diversity, and research memory.

FAMA is now bibliographically identified through AlphaEval's references as **Can Large Language Models Mine Interpretable Financial Factors More Effectively? A Neural-Symbolic Factor Mining Agent Model** (Li et al., Findings of ACL 2024). This remains **S** evidence until its primary paper is reviewed. The application at [RndmVariableQ/AlphaAgent](https://github.com/RndmVariableQ/AlphaAgent) remains distinct from the verified Tang et al. AlphaAgent paper; matching names are insufficient to establish provenance.

## 2. Symbolic features, ASTs, and gradients

The follow-up found a closer match to **optimizing the tree structure itself**: DGP for high-dimensional symbolic regression. FEAT remains a strong match for optimizing numeric weights inside evolved feature trees. These should be separate experiments.

| Newly verified gradient reference | Evidence | Relevance and limit |
|---|---|---|
| **Differentiable Genetic Programming** — Izzo, Biscani, Mereta (2016 preprint; cited as EuroGP 2017 by FEAT) | **A**: [paper](https://arxiv.org/abs/1611.04766) | Differentiable Cartesian GP with high-order automatic differentiation for program outputs and constant fitting. Cartesian graph encoding differs from a conventional AST. |
| **Differentiable Genetic Programming for High-dimensional Symbolic Regression** (2023 preprint) | **F**: [paper](https://arxiv.org/abs/2304.08915) | A differentiable symbolic tree relaxes discrete structure, a gradient optimizer fits it, sampling returns discrete expressions, and a diversification mechanism escapes local optima. This is the most direct retrieved match to gradient-guided tree-structure search. It is general SR, not demonstrated financial alpha mining. |
| **Effects of constant optimization by nonlinear least squares minimization in symbolic regression** — Kommenda et al. (GECCO Companion 2013) | **S**, verified in FEAT's bibliography: [DOI](https://doi.org/10.1145/2464576.2482691) | Numeric fitting inside searched expressions; inspect solver details before equating nonlinear least squares with ordinary neural backpropagation. |
| **Faster genetic programming based on local gradient search of numeric leaf values** — Topchy and Punch (GECCO 2001) | **S**, verified in [FEAT's full text](https://arxiv.org/abs/1807.00981) | Early direct reference for gradient optimization of numeric leaves. Structure remains a separate search problem. |

| Work | Evidence and source | Mechanism | Application to factor mining |
|---|---|---|---|
| **Learning concise representations for regression by evolving networks of trees — FEAT** (La Cava et al., ICLR 2019) | **F/P**: [author repository](https://github.com/lacava/feat); [paper](https://arxiv.org/abs/1807.00981); [method documentation](https://github.com/lacava/feat/blob/master/docs/overview.md) | Evolve symbolic feature representations; fit a downstream model and update weights of differentiable features with stochastic gradient descent. | Closest verified match to gradient-assisted AST feature mining. Evaluate several feature trees jointly instead of searching only for one best equation. |
| **Learning feature spaces for regression with genetic programming** (La Cava and Moore, 2020, as cited in FEAT documentation) | **P**: [method description and reference](https://github.com/lacava/feat/blob/master/docs/overview.md) | Wrapper-based evolution of feature spaces, model fitting, and numeric refinement. | Use an inner model-fitting loop and a complexity-aware archive; substitute finance-specific objectives carefully. |
| **Learning equations for extrapolation and control — Equation Learner / EQL** (Sahoo, Lampert, Martius, ICML 2018) | **P**: [author repository](https://github.com/martius-lab/EQL); [paper](https://proceedings.mlr.press/v80/sahoo18a.html) | Neural-network approach to concise symbolic equations with mathematical operator units. | An alternative differentiable representation. Useful for learning numeric connections/weights and extracting formulas, but it is not unrestricted discrete tree optimization. |
| **Deep symbolic regression: Recovering mathematical expressions from data via risk-seeking policy gradients** (Petersen et al., ICLR 2021) | **P**: [DSO author project](https://github.com/dso-org/deep-symbolic-optimization); [paper](https://openreview.net/forum?id=m5Qsh0kBQG) | A neural policy generates symbolic expressions; policy-gradient training emphasizes high-reward samples. | Learn where to search in a discrete expression grammar. Replace regression reward with a carefully defined financial objective. |
| **Symbolic Regression via Neural-Guided Genetic Programming Population Seeding** (Mundhenk et al., NeurIPS 2021) | **P**: [DSO publication list](https://github.com/dso-org/deep-symbolic-optimization); [paper](https://proceedings.neurips.cc/paper/2021/hash/d073bb8d0c47f317dd39de9c9f004e9d-Abstract.html) | Combine learned generation with genetic-programming refinement. | A practical global-search/local-improvement hybrid. Benchmark whether neural guidance helps beyond simply running more GP evaluations. |
| **A Unified Framework for Deep Symbolic Regression** (Landajuela et al., NeurIPS 2022) | **P**: [DSO project](https://github.com/dso-org/deep-symbolic-optimization); [paper](https://openreview.net/forum?id=2FNnBhwJsHK) | Unified symbolic search with neural and evolutionary mechanisms and enhanced expression handling. | Reference implementation for configurable search tasks, expression constraints, inner optimization, and model archives. |
| **DisCo-DSO: Coupling Discrete and Continuous Optimization for Efficient Generative Design in Hybrid Spaces** (Pettit et al., AAAI 2025) | **P**: [DSO publication list](https://github.com/dso-org/deep-symbolic-optimization); [paper](https://arxiv.org/abs/2412.11051) | Couple discrete choices with continuous optimization in hybrid design spaces. | Relevant to jointly reasoning about operator choices and numeric parameters. Its reported application is not financial factor discovery; transfer needs experimentation. |
| **Interpretable Machine Learning for Science with PySR and SymbolicRegression.jl** (Cranmer, 2023 preprint identifier) | **P** for project and paper link: [PySR](https://github.com/MilesCranmer/PySR); [paper](https://arxiv.org/abs/2305.01582); [backend](https://github.com/astroautomata/SymbolicRegression.jl) | Symbolic expression search with configurable operators and accuracy/complexity tradeoffs. | Mature candidate baseline or external search adapter. Restrict operators and use finance-specific objectives; standard tabular regression is not sufficient validation for market data. |
| **Operon C++: An Efficient Genetic Programming Framework for Symbolic Regression** (Burlacu, Kronberger, Kommenda, GECCO Companion 2020) | **P**: [author project](https://github.com/heal-research/operon); [paper DOI](https://doi.org/10.1145/3377929.3398099) | Efficient expression-tree genetic programming with Python bindings available separately. | Useful for evaluator throughput and a strong native-code baseline. Investigate numeric parameter optimizers in the exact version selected rather than assuming all optimizers use backpropagation. |
| **Linear Scaling with and within Semantic Backpropagation-based Genetic Programming for Symbolic Regression** (Virgolin et al., GECCO 2019) | **P**: [author project and citation](https://github.com/marcovirgolin/GP-GOMEA); **S** paper link from [SRBench](https://github.com/cavalab/srbench): [DOI](https://doi.org/10.1145/3321707.3321758) | Semantic backpropagation guides modification by recursively inverting functions toward desired outputs. | A distinct interpretation of “backprop on trees.” Useful for subtree repair, but inverses may be ambiguous and trees may grow complex. |
| **Improving model-based genetic programming for symbolic regression of small expressions** (Virgolin et al., Evolutionary Computation 2021) | **P**: [GP-GOMEA author project](https://github.com/marcovirgolin/GP-GOMEA) | Learn dependencies between components and recombine useful building blocks together. | Preserve meaningful subtrees while searching for compact formulas; compare to ordinary crossover. |
| **AI Feynman: A physics-inspired method for symbolic regression** and **AI Feynman 2.0: Pareto-optimal symbolic regression exploiting graph modularity** (2020) | **P**: [author code and citations](https://github.com/SJ001/AI-Feynman); [2.0 paper](https://arxiv.org/abs/2006.10782) | Exploit structural properties and modularity to simplify equation discovery. | Inspiration for decomposition and complexity-aware search. Financial signals are noisy and nonstationary; success on physical equations does not establish transfer. |
| **Contemporary Symbolic Regression Methods and their Relative Performance — SRBench** (La Cava et al., NeurIPS Datasets and Benchmarks 2021) | **P**: [benchmark](https://github.com/cavalab/srbench); [paper](https://arxiv.org/abs/2107.14351) | Compare modern symbolic regression with common datasets and interfaces. | Adopt common protocols, independent seeds, cost reporting, and strong baselines. Ordinary SR benchmarks are complementary to financial evaluation. |

### Five different meanings of backpropagation

1. **Numeric differentiation through a fixed expression.** Given a structure such as `a * rolling_mean(close, 20) + b * volume`, differentiate with respect to `a` and `b`. This does not choose a different operator or rolling-window length. FEAT is the most directly supported reference above; [QuickSR's implementation/report](https://github.com/kocatepedogu/quick-symbolic-regression) also explicitly describes forward/backward bytecode and gradient fitting of tree parameters. QuickSR is an engineering reference, not a verified peer-reviewed financial paper.
2. **Policy gradients for structure generation.** Optimize parameters of a distribution over discrete expressions. DSR and AlphaGen belong in this category; the reward need not be differentiable with respect to the expression.
3. **Continuous relaxation of discrete structure.** Mix candidate operators with differentiable weights, optimize the mixture, then discretize it. DGP explicitly relaxes symbolic trees. AlphaForge uses a differentiable predictor of fitness and Gumbel-Softmax generation; its gradients flow through that surrogate, not through exact realized portfolio returns. EQL provides a related differentiable symbolic architecture; DARTS and Gumbel-Softmax are general methodological references. Soft and discretized models can behave differently.
4. **Semantic backpropagation.** Propagate desired output behavior through inverse operations to guide subtree changes. This is not ordinary reverse-mode differentiation.
5. **MCTS backup.** Propagate evaluated rewards or learned values to ancestor search nodes to update visit/value statistics. AlphaCFG and FactorEngine use this meaning too. It does not differentiate an AST; the neural value/policy network is trained separately.

For finance, `rank`, discrete lags/windows, comparisons, branching, and some missing-value policies are not smoothly differentiable. Differentiable rolling averages can coexist with nondifferentiable structure choices. Soft ranks, continuous windows, or straight-through estimators require explicit approximation tests. Never silently substitute them for the exact operator used in validation and trading.

A reasonable first hybrid is outer-loop tree search plus inner-loop fitting of continuous coefficients, with a small ridge-regression or gradient-based optimizer. Fit everything on training data, select on validation, freeze both structure and coefficients for the untouched test. Do not continually tune constants on the test period.

Follow with two distinct comparisons: (a) DGP-style relaxed tree search versus ordinary GP using exact financial evaluation after discretization, and (b) AlphaForge-style surrogate-guided generation versus policy-gradient proposals. Monitor surrogate error and the gap between relaxed and exact scores; refresh the surrogate using actual evaluations rather than letting it invent the final score.

## 3. Exploration versus exploitation

Exploration spends evaluations on uncertain or structurally different candidates; exploitation spends them improving currently promising candidates. Financial search also needs **diversity**: several moderately strong, weakly correlated signals may be more useful than many variations of one high-scoring signal.

| Mechanism | Closest verified reference | What to test | Failure mode |
|---|---|---|---|
| Random search and random restarts | [gplearn](https://github.com/trevorstephens/gplearn) and [SRBench](https://github.com/cavalab/srbench) as implementation/benchmark references | Same grammar and number of unique evaluations as learned miners | Weak candidates, but indispensable as a budget-matched baseline |
| Mutation, crossover, and hierarchical reuse | AutoAlpha; GP-GOMEA | Diversity, useful subtrees, complexity, and cost versus ordinary GP | Premature convergence, expression bloat, repeated equivalent formulas |
| Entropy-regularized policy generation | AlphaGen; AlphaSAGE's documented entropy controls | Diversity and factor quality across entropy schedules and seeds | High entropy can waste the budget; low entropy can collapse the pool |
| Reward-tail or elite-sample optimization | DSR; unified DSR | Sensitivity to elite thresholds and reward noise | Overfitting to lucky high-scoring candidates |
| Distributional action values | AlphaQCM | Whether uncertainty-guided choices improve held-out archive quality | Reward variability mistaken for lack of knowledge |
| Diverse reward-weighted generation | AlphaSAGE; GFlowNets | Effective number of distinct, economically useful signal clusters | Different strings that evaluate almost identically; reward-scale sensitivity |
| Bayesian retrieval of parents | AlphaPROBE | Benefit per expensive offspring evaluation; posterior calibration | Overconfident retrieval and repeated exploitation of a misleading parent |
| Grammar-aware tree search | RiskMiner; AlphaCFG; Navigating the Alpha Jungle | Benefit of value-guided branching and intermediate feedback per exact evaluation | MCTS backup confused with gradients; optimistic noisy rewards and excessive branching cost |
| Logic search plus numeric search | FactorEngine; FEAT; DGP | Separate structure changes, parameter fitting, and evaluation costs | Numeric fitting overused validation or relaxed expressions fail after discretization |
| Neural proposals followed by local evolution | Neural-guided GP; HARLA | Compare under the same evaluation and compute/token budgets | Improvements explained only by spending more compute |
| Structural and behavioral novelty archives | AlphaSAGE; AutoAlpha; GP-GOMEA | Marginal contribution after controlling redundancy and exposures | Maximizing novelty without predictive value |

### GFlowNet and exploration references

- **Flow Network based Generative Models for Non-Iterative Diverse Candidate Generation** (Bengio et al., 2021). **P**: [author implementation](https://github.com/GFNOrg/gflownet), [paper](https://arxiv.org/abs/2106.04399). Learn a distribution over useful candidates rather than targeting only a single optimum. A finance implementation must define rewards and handle duplicate paths/expressions carefully.
- **Improving exploration in policy gradient search: Application to symbolic optimization** (Landajuela et al., Math-AI workshop at ICLR 2021). **P**: [DSO publication list](https://github.com/dso-org/deep-symbolic-optimization), [paper](https://mathai-iclr.github.io/papers/papers/MATHAI_16_paper.pdf). Particularly relevant to exploration in symbolic search; workshop results need broader financial validation.

### General methodological references to verify before implementation

These **B** references complete the method map; they are not financial-alpha evidence and their full text was not inspected here.

| Reference | Link | Role |
|---|---|---|
| **Finite-time Analysis of the Multiarmed Bandit Problem** (Auer, Cesa-Bianchi, Fischer, 2002) | [DOI](https://doi.org/10.1023/A:1013689704352) | Upper-confidence-bound selection of search strategies or factor families; stationary-bandit assumptions do not automatically hold during adaptive search. |
| **On the Likelihood that One Unknown Probability Exceeds Another in View of the Evidence of Two Samples** (Thompson, 1933) | [DOI](https://doi.org/10.1093/biomet/25.3-4.285) | Posterior sampling for allocating evaluations; posterior modeling must reflect the actual noisy objective. |
| **Bandit based Monte-Carlo Planning** (Kocsis and Szepesvári, 2006) | [DOI](https://doi.org/10.1007/11871842_29) | UCT / Monte Carlo tree search over partial expressions; delayed rewards, grammar legality, and caching need explicit design. |
| **Proximal Policy Optimization Algorithms** (Schulman et al., 2017) | [paper](https://arxiv.org/abs/1707.06347) | Policy optimization foundation for an AlphaGen-style baseline. |
| **Distributional Reinforcement Learning with Quantile Regression** (Dabney et al., 2018) | [paper](https://arxiv.org/abs/1710.10044) | Quantile-based value distributions behind distributional-RL designs. |
| **Implicit Quantile Networks for Distributional Reinforcement Learning** (Dabney et al., 2018) | [paper](https://arxiv.org/abs/1806.06923) | Flexible return-distribution approximation; inspect exploration assumptions separately. |
| **Trajectory Balance: Improved Credit Assignment in GFlowNets** (Malkin et al., 2022) | [paper](https://arxiv.org/abs/2201.13259) | Candidate training objective for reward-weighted generation over expression trajectories. |
| **DARTS: Differentiable Architecture Search** (Liu et al., 2019) | [paper](https://arxiv.org/abs/1806.09055) | Inspiration for continuous relaxation of operator choices; not direct proof of differentiable financial AST mining. |
| **Categorical Reparameterization with Gumbel-Softmax** (Jang, Gu, Poole, 2017) | [paper](https://arxiv.org/abs/1611.01144) | Differentiable approximation to discrete selections; test temperature and discretization behavior. |

Do not immediately implement every search strategy. Add a method only when it addresses an observed problem in the current search, and compare its incremental benefit under a fixed budget.

## 4. Industry relevance, baselines, and statistical validity

### What “close to industry” is supported by the sources

| Work | Concrete evidence inspected | What is still unestablished |
|---|---|---|
| AlphaForge | The PDF's “Simulated Trading and Real Money Investment” section reports a real CSI500 account with 3 million RMB and approximately nine months of investment, alongside simulation. | No independent account audit, verified ongoing performance, or generalizable capacity estimate was obtained. This is the strongest retrieved direct live-account claim among the selected full-text checks. |
| AlphaPROBE | Author repository lists a quantitative investment firm affiliation; primary abstract describes evaluation across Chinese equity datasets. | Affiliation and backtests do not establish live use. |
| AgonAlpha | Primary abstract reports deployments and graded submissions on WorldQuant BRAIN with prompt-to-expression provenance. | Platform evaluation and grades do not establish audited realized trading returns; full method review remains pending. |
| FactorEngine | PDF specifies commissions, sell-side stamp duty, slippage, lot constraints, daily-volume caps, price limits, and a walk-forward downstream model. | Historical simulations remain dependent on data quality, timing, implementation fidelity, and repeated selection; no independent live result was verified. |
| AlphaGen / AlphaQCM | Applied financial search with public code; AlphaGen is an Applied Data Science paper and AlphaQCM has an official ICML 2025 proceedings/code entry. | Publication and reproducible source do not establish actual production deployment. |
| Qlib / RD-Agent-Quant | Microsoft-maintained research tooling with documented factor/model/backtest workflows and public interfaces. | A framework's maturity does not validate every strategy built with it. |
| FEAT / DGP / EQL | Explicit mechanisms for symbolic feature construction or differentiable structure learning, with accessible papers or author implementations. | Transfer to nonstationary financial data and execution-constrained portfolios remains an experiment. |

### Verified project references

- **Qlib: An AI-oriented Quantitative Investment Platform** (2020 preprint identifier). **P**: [Microsoft project](https://github.com/microsoft/qlib), [paper](https://arxiv.org/abs/2009.11189). Useful reference for research workflows, feature baselines, model training, portfolio backtesting, and execution. Keep Qlib optional behind an adapter; the mining framework must still consume the repository's CSV/SQLite contract independently.
- **101 Formulaic Alphas** (Kakushadze, 2016). **A/S**: [primary abstract](https://arxiv.org/abs/1601.00991) and the inspected [AutoAlpha reproduction](https://github.com/bigsuperFishfish/AutoAlpha). Useful hand-designed formula baseline and operator vocabulary. Confirm original definitions and implementation semantics before comparing against mined factors; a formula list is not evidence of current profitability.
- **A flexible symbolic regression method for constructing interpretable clinical prediction models** (La Cava et al., npj Digital Medicine 2023). **P**: [FEAT project reference](https://github.com/lacava/feat), [paper](https://www.nature.com/articles/s41746-023-00833-8). An applied feature-construction example outside finance, useful for interpretability and validation design. Clinical results do not demonstrate trading performance.

### Finance and evaluation background to add to the reading queue

These **B** references are relevant safeguards or non-symbolic baselines. They were not independently retrieved during this search and should receive a primary-source review before extracting detailed claims.

- **Empirical Asset Pricing via Machine Learning** — Gu, Kelly, Xiu (2020), [DOI](https://doi.org/10.1093/rfs/hhaa009). Establish strong conventional return-prediction baselines; a symbolic miner should compete with simpler linear and tree-based alternatives.
- **Autoencoder Asset Pricing Models** — Gu, Kelly, Xiu (2021), [NBER working paper](https://www.nber.org/papers/w25492). A latent-factor approach to contrast with interpretable formulaic features.
- **Characteristics Are Covariances: A Unified Model of Risk and Return** — Kelly, Pruitt, Su (2019), [NBER working paper](https://www.nber.org/papers/w24540). Instrumented PCA is a useful latent-factor comparator; risk-factor modeling and alpha prediction should remain distinct tasks.
- **… and the Cross-Section of Expected Returns** — Harvey, Liu, Zhu (2016), [DOI](https://doi.org/10.1093/rfs/hhv059). Relevant to multiple testing in the factor zoo; automated search increases rather than removes that problem.
- **The Probability of Backtest Overfitting** — Bailey et al. (2017), [DOI](https://doi.org/10.21314/JCF.2016.322). Evaluate sensitivity to repeated strategy selection. Its methodology is not a substitute for time-aware, leakage-free evaluation.
- **The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality** — Bailey and López de Prado (2014), [DOI](https://doi.org/10.3905/jpm.2014.40.5.094). Useful selection-bias diagnostic; record search trials and assumptions needed for its use.
- **A Reality Check for Data Snooping** — White (2000), [DOI](https://doi.org/10.1111/1468-0262.00152). Compare a family of adaptively considered strategies with dependence-aware resampling.
- **A Test for Superior Predictive Ability** — Hansen (2005), [DOI](https://doi.org/10.1198/073500105000000063). Further reference for comparisons under multiple competing models.
- **Trading Costs** — Frazzini, Israel, Moskowitz, [working paper](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3229719). Industry-oriented execution-cost reference. Inspect trading universe, scale, and cost assumptions before transferring estimates.

### Evaluation requirements for this repository

1. **Point-in-time inputs.** Record event time and availability time separately for fundamentals, alternative data, and revisions. Avoid survivorship bias in universes and preserve delisted instruments. Define corporate-action handling explicitly.
2. **Causal operator evaluation.** Factor values at time `t` may use only information available by the decision time. Labels may use future observations but must never become candidate features. Define rolling-window alignment and whether today's close is tradable before or after signal construction.
3. **Temporal validation.** Use chronological train/validation/test splits, with purging of overlapping label intervals and embargo where justified. Fit normalization, neutralization coefficients, selection, and learned preprocessing within the training process. Repeated validation reuse also causes overfitting; retain a genuinely untouched final evaluation.
4. **Strong baselines.** Include simple momentum/reversal signals, fixed formulas, random search, GP, regularized linear models, and a conventional boosted-tree predictor. Report what each comparison actually tests.
5. **Comparable budgets.** Record unique full-data evaluations, total proposals, wall time, hardware, optimizer steps, memory, and LLM calls/tokens/cost. Cached evaluations and surrogate scores must be reported separately.
6. **Signal diagnostics.** Report mean daily cross-sectional IC and rank IC, their variability with an explicitly defined ICIR convention, coverage, factor correlation, quantile behavior, turnover, and exposures. Show behavior across subperiods and universes. Define missing-value and degenerate-correlation handling.
7. **Portfolio diagnostics.** Use explicit construction, rebalance time, holding periods, costs, slippage, liquidity/participation constraints, borrowing limits, and benchmark. Report net returns, Sharpe with documented annualization, drawdown, turnover, and capacity sensitivity. Long-only and long-short results are not interchangeable.
8. **Selection accounting.** Save every evaluated candidate, rejected candidates, search settings, and selection rounds. Consider dependence-aware uncertainty estimates and multiple-testing adjustments. More discovered formulas does not mean more independent evidence.
9. **Ablations and seeds.** Compare pool-aware versus single-factor rewards, structural versus behavioral novelty, gradient refinement on/off, learned proposals versus random proposals, and exact versus relaxed operators. Report dispersion across independent runs, not only the best seed.
10. **Reproducibility.** Pin code and dataset versions, save manifests and splits, operator semantics, expression serialization, fitted parameters, and experiment configuration. A claimed reproducible backtest should be rerunnable from the published dataset artifact without a downloader or live external API.

## 5. Architecture informed by the papers

Keep the mining package separate from `data-pipeline/`. Its only data dependency is the [dataset artifact contract](../docs/DATA_CONTRACT.md). Under the [component architecture](../docs/ARCHITECTURE.md), training and inference live in mining; trading strategies and the backtest engine live in `data-pipeline/strategy-evaluation/`. The interfaces below describe the overall research workflow. Portfolio feedback crosses an artifact boundary rather than importing the simulator into mining. Any financial metadata the generic contract does not yet describe needs a reviewed extension, not a hidden import of pipeline state.

```text
CSV / SQLite bundle + manifest
             |
     read-only data adapter
             |
   point-in-time panel and splits
             |
       typed AST evaluator <---- search strategy
             |                       |
      candidate diagnostics ---- feedback
             |
    diverse, versioned factor archive
             |
   train-only combination / model fitting
             |
     frozen walk-forward evaluation
             |
 expressions + parameters + reports + provenance
```

Recommended independent interfaces:

- **Dataset reader:** validate the bundle and expose aligned timestamps, instrument identifiers, features, and availability metadata. No downloading or cleaning service dependency.
- **Operator registry:** type signatures, units, lookback, causal alignment, missing-data behavior, exact evaluation, and optional derivatives. Grammar masks reject invalid expressions before costly evaluation.
- **Expression representation:** canonical, versioned AST serialization and hashes. Start with immutable trees; use DAGs for shared subexpression evaluation or evolutionary lineage when justified. Syntax equivalence and empirical similarity are different kinds of deduplication.
- **Evaluator:** compute training rewards and separate validation diagnostics using explicit split identifiers. Cache by dataset version, split, expression, numeric parameters, and operator version. Never reuse a training score as a test score.
- **Searcher:** propose expressions without owning the data source or portfolio simulator. Support random search, GP, policy-based proposals, and later GFlowNets through the same interface.
- **Parameter fitter:** fit constants and differentiable weights for a fixed structure on training data; return frozen parameters and optimizer provenance.
- **Archive and selector:** retain a Pareto set of quality, complexity, turnover, and behavioral diversity; measure marginal predictive contribution. Correlation alone does not capture all redundancy or risk exposures.
- **Combination and backtester:** fit combinations separately, apply realistic execution assumptions, and preserve the distinction between signal quality and portfolio returns.
- **Experiment recorder:** save budgets, seeds, candidates, split definitions, source versions, failures, and results. Include LLM prompts/model versions when relevant; exclude secrets.

For daily cross-sectional data, a proposed logical key is `(timestamp, instrument_id)`. Add explicit target horizon, feature availability rules, trading calendar, timezone, units, and universe policy as mining metadata. This proposal does not silently change version 1 of the existing contract.

## 6. Staged implementation and tests

| Stage | Deliverable | Reading priority | Completion evidence |
|---|---|---|---|
| 1 | Read-only CSV/SQLite adapter, typed AST, causal evaluator, manifests and splits | Qlib; AlphaGen calculator interface; AlphaEval | Independent dataset fixtures; exact operator tests; future-data perturbations cannot change earlier signals; duplicate and invalid expressions rejected |
| 2 | Random search, GP, cached evaluator, diverse archive, fixed baselines | AutoAlpha; gplearn; GP-GOMEA; SRBench | Budget-matched reproducible comparisons; equivalent expressions identified; expected results on synthetic known-signal data |
| 3 | Numeric fitting for fixed ASTs; separately fitted combinations | FEAT; EQL; DisCo-DSO; DGP | Analytic or finite-difference gradient checks on smooth operators; known-coefficient recovery; training-only fitting; exact exported expression matches fitted evaluation |
| 4 | Pool-aware learned proposals and hybrid GP refinement | AlphaGen; DSR; neural-guided GP; AlphaForge | Incremental archive quality versus GP/random at equal budgets; independent seeds and reward ablations |
| 5 | Uncertainty/diversity experiments | AlphaQCM; RiskMiner; AlphaCFG; AlphaSAGE; AlphaPROBE; GFlowNets | Held-out benefit from exploration mechanism; structural and signal diversity; reward-scale and uncertainty-calibration sensitivity |
| 6 | Optional LLM hypothesis and implementation assistance | HARLA; R&D-Agent-Quant | Sandboxed execution of generated code, saved hypotheses, reproducible numerical checks, token/cost budgets, and no holdout feedback in the agent loop |
| 7 | Walk-forward portfolio validation and operational review | AlphaEval; finance/statistical background | Net-of-cost robustness, capacity/exposure diagnostics, complete trial ledger, untouched evaluation, then prospective paper trading |

Unit tests should cover types, operators, derivatives, canonicalization, serialization, and masks. Integration tests should consume independent bundles and exercise the full candidate-to-report path. Synthetic planted-signal tests verify pipeline mechanics but do not establish financial profitability. LLM output must never be executed as unrestricted Python; a constrained expression DSL is preferable for ordinary factor proposals.

## 7. Questions to resolve before selecting a miner

- Is the immediate goal interpretable alpha discovery, risk-factor discovery, or predictive feature engineering? These need different targets and validation.
- What market, frequency, holding horizon, decision time, and execution rules apply?
- Are price/volume inputs enough, or are point-in-time fundamentals and alternative data available?
- Which operators are meaningful and legal, and which support reliable numeric derivatives?
- Is the objective one strong factor, a diversified library, or a downstream portfolio? How will turnover and exposures enter selection?
- What is the evaluation budget, and will neural/LLM methods be affordable relative to GP?

Until those decisions are made, implement the common representation and evaluator rather than committing the framework to a single research paper.

## Source trail

The live discovery searches included AlphaForge, AlphaGen, AlphaQCM, AlphaSAGE, AlphaPROBE, AutoAlpha, AlphaEval, alpha mining, and symbolic regression backpropagation on [GitHub repository search](https://github.com/search?type=repositories). Author and benchmark sources used are linked alongside their entries. Inspected sources included the AlphaGen calculator documentation, AlphaQCM's `train_qcm.py`, FEAT's `docs/overview.md`, and the publication lists in DSO, GP-GOMEA, SRBench, Qlib, and RD-Agent.

The follow-up successfully queried arXiv and OpenAlex and inspected ICML 2025 proceedings. Relevant sections of PDFs were checked for AlphaForge, RiskMiner, AlphaAgent, AlphaSAGE, AlphaEval, AlphaCFG, FactorEngine, FEAT, and DGP. The [catalog](PRIMARY_SOURCE_CATALOG.md) records the broader abstract-level discovery set. Publisher pages and background references not explicitly upgraded above remain unverified in this session. Recheck publication versions, licenses, and experiment details before adopting code or citing numeric results.
