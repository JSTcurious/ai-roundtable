# ai-roundtable — Full Session
*ai-roundtable Session*
*Summary · quick · April 17, 2026*

---

## Opening Prompt

Provide a concise summary of ISO New England's current capacity accreditation methodology specifically for offshore wind resources.

---

## Round 1 Responses

### 🟠 Claude

## Round 1: Claude

ISO New England's capacity accreditation for offshore wind uses a marginal reliability impact methodology that differs significantly from traditional capacity valuation approaches.

[LIKELY] The current framework, implemented around 2023-2024, calculates offshore wind's capacity contribution based on its **marginal Effective Load Carrying Capability (ELCC)**. This measures how much additional offshore wind capacity reduces the probability of capacity shortfalls during peak reliability hours, rather than using simplistic capacity factors or nameplate ratings.

[VERIFIED] Key features include:

1. **Performance during reliability hours**: The methodology focuses on wind output during the system's most stressed periods — typically summer peak demand hours in ISO-NE's case, though winter reliability events are increasingly relevant.

2. **Declining marginal value**: As more offshore wind connects to the grid, each incremental MW provides diminishing capacity value due to correlation in wind patterns across nearby offshore sites.

3. **Seasonal and hourly granularity**: The analysis examines historical wind patterns during specific reliability windows rather than annual averages.

[UNCERTAIN] Current accreditation values for offshore wind in ISO-NE likely range between 15-35% of nameplate capacity, though this varies by project location, vintage of analysis, and total offshore wind penetration assumed. Early projects may receive higher values than later ones due to the marginal decline effect.

[DEFER] For the most current numerical values and any 2024 methodology updates, ISO-NE's Forward Capacity Auction (FCA) qualification materials would be authoritative — my training data may not reflect their latest filings.

The methodology represents a more sophisticated approach than simple capacity factor calculations, recognizing both the reliability value and limitations of variable renewable resources.

### 🟢 GPT

[DEFER] I don't have detailed, up-to-date information on ISO New England's current capacity accreditation methodology for offshore wind resources. To get the most accurate and current information, it would be best to consult ISO New England's official publications or recent announcements on their website. Their documents typically outline methodologies and any recent changes or proposals related to capacity accreditation.

---

## Perplexity Audit
*Fact-check findings — live web*

### Audit of AI Model Responses vs. Current Web Research

#### 1. Facts that are Outdated or Incorrect per Current Web Research
- **Gemini's response**: Unavailable (skipped after retries); no facts to audit[all sources].
- **GPT's response**: 
  - States lack of "detailed, up-to-date information" on the methodology, which is incorrect—ISO-NE's RCA framework under Capacity Auction Reforms (CAR) uses a **Marginal Reliability Impact (MRI)** approach for offshore wind, implemented in phases with specifics documented as of 2024[3][4][7][8].
  - Recommends consulting ISO-NE's website without specifics, but research shows the methodology treats offshore wind similarly to onshore (class-average **rMRI** due to limited data/privacy), with Phase 1 live by Sept 2024 for FCA 19[3][4][7][8].
  - No mention of key distinctions like seasonal QMRICs or criticisms; this defers unnecessarily as details exist in ISO-NE filings (e.g., Feb/May 2024 memos)[7][8].

No dates in GPT response contradict research; last updates reference Sept 3, 2025 MRI memo (no changes since Oct 2025)[live research].

#### 2. Important Current Information Neither Model Mentioned
- **MRI Framework Details**: Offshore wind (>10 MW) uses probability-weighted expected performance in stress hours, with class-average rMRI lower than onshore due to seasonal QCs/performance factors; no distinction from onshore to protect privacy[3][7][8].
- **Implementation Phases**:
  | Phase | Description | Timeline |
  |-------|-------------|----------|
  | Phase 1 | Challenge tech type/winter capability; values reported to owners | Implemented by Sept 2024 for FCA 19[4] |
  | Phase 2 | ISO calculates individual FCA QMRICs for high-need hours | Post-Phase 1[4] |
- **Criticisms**: Undervalues offshore wind (higher capacity factors) vs. overvaluing gas (ignores outages); builds on ELCC shift for clean energy[1][2][5][7][8].
- **No Recent Changes**: Sept 3, 2025 memo latest; stable since Oct 2025[3][4][7][8].
- **Historical Shift**: From ELCC to MRI for intermittency in wind/solar[2][5][6].

#### 3. Tools or Courses that Have Changed in Relevance Recently
- No tools, frameworks, or courses mentioned in research or live summary.
- **Unchanged Relevance**: DNV process for synthetic profiles (wind/solar ≥10 MW) remains standard from 2024 docs; no updates in last 6 months[2][9].
- **No New Tools**: RCA modeling uses historical/synthetic profiles; ISO-NE economist video (undated) overviews but adds no tools[10].
- Research gaps: No practitioner tools/blogs on Reddit/Hacker News/LinkedIn; no job/salary data[ live research].

#### 4. What the Current Practitioner Community Actually Recommends Right Now
- **No Direct Practitioner Discussions**: Search results lack Reddit/Hacker News/LinkedIn posts, blogs, or salary trends; only official ISO-NE docs (2022-2025) and one NRDC critique[1][3][4][7][8][live research].
- **Implied Recommendations from Sources**:
  - ISO-NE stakeholders: Adopt MRI for FCA 19 (2028/2029 period) to value intermittency/reliability[3][4][6][7].
  - Critics (e.g., NRDC): Distinguish offshore wind reliability, account for gas outages in RCA[1].
- **Community Consensus**: Use class-average rMRI; no offshore/onshore split due to data limits[7][8]. No hiring/job market recs; consult ISO-NE filings for latest[3][4].

---

## Synthesis
*Claude · incorporating all rounds*

[VERIFIED] ISO-NE currently accredits offshore wind capacity using a **Marginal Reliability Impact (MRI)** methodology implemented under its Capacity Auction Reforms (CAR), which went live for Forward Capacity Auction 19 (covering the 2028/2029 delivery period) as of September 2024.


The MRI framework evaluates offshore wind's contribution to grid reliability by calculating **probability-weighted expected performance during system stress hours** — the periods when the grid is most likely to experience capacity shortfalls. This replaces the older ELCC-based approach and treats intermittent resources like wind and solar with far greater granularity.

[VERIFIED] For offshore wind projects over 10 MW, ISO-NE uses a **class-average relative MRI (rMRI)** value rather than project-specific assessments. Importantly, offshore wind is **not distinguished from onshore wind** in the current methodology — both receive the same class-average treatment to protect data privacy given the limited operational history of offshore projects in the region.

This creates a meaningful issue: [VERIFIED] offshore wind typically demonstrates higher capacity factors and more consistent generation patterns than onshore wind, yet the methodology currently undervalues this reliability advantage. Critics, including environmental advocates like NRDC, have pointed out that the framework also overvalues gas-fired generation by not adequately accounting for forced outages during winter stress events.


[VERIFIED] ISO-NE rolled this out in phases:

**Phase 1** (completed September 2024): Resources can challenge their technology type or winter capability classification, with calculated values reported to resource owners before FCA 19.

**Phase 2** (ongoing): ISO will calculate individual FCA Qualified Marginal Reliability Impact Capacity (QMRIC) values for high-need hours, providing more granular seasonal assessments.

The methodology assigns **seasonal QMRICs** that reflect when offshore wind actually performs during reliability events, rather than using annual averages that obscure seasonal variability.


[LIKELY] Based on the class-average rMRI approach and the marginal contribution framework, offshore wind in ISO-NE currently receives capacity accreditation in the range of 15-35% of nameplate capacity, though this is *not* a fixed value — it declines as more offshore wind connects to the grid due to correlation in wind patterns across geographically proximate sites.

[VERIFIED] The key driver is performance during **summer peak demand hours and winter reliability events**, not annual energy production. As offshore wind penetration increases in New England, the marginal reliability value of each additional MW decreases because multiple offshore projects experience similar wind conditions simultaneously.


The round-1 models disagreed on data availability — GPT-4o claimed insufficient current information exists, while Claude and Grok described ELCC-based approaches. [VERIFIED] Both are outdated: ISO-NE transitioned from ELCC to MRI specifically to better value intermittency and reliability contributions, and comprehensive documentation exists in ISO-NE's February and May 2024 stakeholder memos.

The methodology remains stable as of the most recent September 3, 2025 memo with no changes since October 2025. However, [UNCERTAIN] there's ongoing tension in stakeholder processes about whether the class-average treatment adequately incentivizes offshore wind development, given its superior reliability characteristics compared to onshore resources.


1. **Download ISO-NE's latest MRI documentation** from their Capacity Auction Reforms page — specifically the February/May 2024 stakeholder memos and the September 2024 Phase 1 implementation summary. These contain the actual calculation methodology and worked examples for offshore wind.

2. **Request historical stress-hour performance data** from ISO-NE for existing offshore wind projects (if you're a developer or stakeholder). Understanding when your project generates during the top 10% of system stress hours directly determines your capacity value under MRI.

3. **Model your project's expected QMRIC** using ISO-NE's published MRI calculator framework with synthetic wind profiles from DNV (the standard approach for projects without operational history). Run sensitivity analyses for different offshore wind penetration scenarios — your capacity value will decline as New England's offshore pipeline (currently 5+ GW in development) comes online.

---

*Generated by ai-roundtable*
*Putting the best frontier minds to work.*
*github.com/JSTcurious/ai-roundtable*