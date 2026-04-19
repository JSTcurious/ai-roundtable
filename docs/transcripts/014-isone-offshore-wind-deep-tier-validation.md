# ai-roundtable — Full Session
*ai-roundtable Session*
*factual answer · deep · April 19, 2026*

---

## Opening Prompt

What is ISO New England's current capacity accreditation methodology for offshore wind?

---

## Round 1 Responses

### 🟠 Claude

ISO New England's capacity accreditation methodology for offshore wind is an evolving area that I need to address carefully given the regulatory complexity involved.

[LIKELY] ISO-NE has been transitioning away from traditional capacity accreditation approaches toward methodologies that better reflect the reliability contribution of intermittent resources like offshore wind. The region has been developing what's called a "marginal reliability impact" (MRI) or similar probabilistic framework that attempts to measure how much a resource actually contributes to meeting peak demand during stressed system conditions.

[UNCERTAIN] Specifically for offshore wind, ISO-NE has been grappling with how to assign capacity values given that:
1. The region has limited operational history with large-scale offshore wind
2. Offshore wind generation profiles differ significantly from onshore wind (typically higher capacity factors, different diurnal patterns)
3. There's correlation risk during winter peak events when multiple offshore facilities might see reduced output simultaneously

[LIKELY] The methodology likely involves an Effective Load Carrying Capability (ELCC) approach or a variant thereof, which calculates what fraction of nameplate capacity can be reliably counted toward meeting reserve margins. For offshore wind, early estimates have suggested ELCC values in the range of 20-40% of nameplate, though this is highly sensitive to assumptions about fleet diversity and weather correlation.

[DEFER] For the precise current methodology—including any recent tariff changes, specific capacity values being applied in Forward Capacity Auctions, or updates from NEPOOL stakeholder processes—I'd recommend checking ISO-NE's official documentation or recent FERC filings, as this has been actively debated and may have evolved beyond my training data.

What aspects of the accreditation approach are most relevant to your inquiry?

### 🔵 Gemini

The premise of your question—that there is a single, stable "current" methodology—is the first thing we should challenge. ISO New England is in the midst of a fundamental, multi-year shift away from a simplistic historical performance model to a more complex probabilistic one. Therefore, the "current" answer is one of transition.

The new framework, broadly known as Resource Capacity Accreditation (RCA), is moving all resources, including offshore wind, to a methodology based on **Marginal Reliability Impact (MRI)**. This is conceptually identical to what other grid operators call Effective Load Carrying Capability (ELCC).

Here’s the breakdown of this transition:

1.  **The Legacy Method (Being Phased Out):** For years, a new renewable resource's initial capacity value was based on a marginal analysis, but its ongoing qualification was tied to its measured performance during a specific, limited set of peak hours. This was a backward-looking, empirical calculation that was criticized for failing to capture the diminishing reliability returns as more of a single type of intermittent resource is added to the grid.

2.  **The New Method (Being Phased In):** The MRI approach is a forward-looking, probabilistic model. It doesn't ask "How did this resource perform during last year's five peak hours?" Instead, it asks, "If we add this specific offshore wind project to the grid of the future, how much additional load can the entire system reliably serve?"

The core logic of MRI is this:
*   The model runs thousands of simulations of a future year, accounting for variable weather, generator outages, and fluctuating demand.
*   It calculates the system's overall reliability (e.g., the risk of a shortfall) *without* the new wind farm.
*   It then adds the wind farm to the model and calculates how much more load would need to be added to the system to return to the *exact same* level of reliability risk as before.
*   That amount of added load is the "Effective Capacity" or accredited capacity of the wind farm.

[LIKELY] This MRI-based methodology has been approved by FERC and is being implemented over a series of Forward Capacity Auctions (FCAs). For offshore wind, the initial capacity values for projects entering the queue are now determined using this probabilistic approach.

The crucial implication, and the reason for the change, is that MRI captures **correlated performance**. The first gigawatt of offshore wind may have a high capacity credit because its output is often uncorrelated with other system risks. However, the tenth gigawatt, whose output will be highly correlated with the first nine, will have a progressively lower marginal reliability impact and therefore receive a lower capacity accreditation value. The system doesn't gain the same reliability benefit from the 10th unit as it did from the 1st.

So, to directly answer your question: ISO New England's current methodology for offshore wind accreditation is a transition to a fully probabilistic, Marginal Reliability Impact model. The specific values are not static; they are the output of a complex model that will be re-run for future auctions and will change as the resource mix on the New England grid evolves.

### 🟢 GPT

[DEFER] I don't have access to the most current details on ISO New England's capacity accreditation methodology for offshore wind. ISO New England typically reviews and updates its methodologies periodically. For the most up-to-date and accurate information, I recommend reviewing ISO New England's official reports or contacting them directly.

---

## Perplexity Audit
*Fact-check findings — live web*

### 1. Verification of EVERY Specific Factual Claim

I systematically verified each distinct factual claim (including named entities, dates, statistics, methodologies, timelines, and implications) from all four Round-1 responses against the Pre-Research Context and provided Search Results [1-10]. Claims are quoted verbatim where possible, followed by accuracy assessment, correction if needed, supporting citation(s), and my confidence level (High: directly confirmed by multiple sources; Medium: confirmed by Pre-Research or single source with context; Low: inferred or unconfirmed).

#### gemini Claims
- "ISO New England is in the midst of a fundamental, multi-year shift away from a simplistic historical performance model to a more complex probabilistic one." **Accurate.** Matches Pre-Research Context on RCA transition from legacy empirical methods to probabilistic MRI[1][7][9]. *Confidence: High.*
- "The new framework, broadly known as Resource Capacity Accreditation (RCA), is moving all resources, including offshore wind, to a methodology based on **Marginal Reliability Impact (MRI)**." **Accurate.** RCA uses MRI (equivalent to ELCC marginal approach) for all resources including offshore wind[1][4][5]. *Confidence: High.*
- "This is conceptually identical to what other grid operators call Effective Load Carrying Capability (ELCC)." **Accurate.** Pre-Research explicitly notes RCA builds on ELCC with marginal approach[1][4][5]. *Confidence: High.*
- "For years, a new renewable resource's initial capacity value was based on a marginal analysis, but its ongoing qualification was tied to its measured performance during a specific, limited set of peak hours." **Accurate.** Describes legacy method phased out in RCA[1]. *Confidence: Medium.*
- "The MRI approach... runs thousands of simulations of a future year, accounting for variable weather, generator outages, and fluctuating demand." **Accurate.** Core logic of probabilistic MRI in RCA[1][7][9]. *Confidence: High.*
- "It calculates the system's overall reliability (e.g., the risk of a shortfall) *without* the new wind farm... adds the wind farm... how much more load would need to be added to... return to the *exact same* level of reliability risk... That amount... is the 'Effective Capacity'." **Accurate.** Precise description of MRI calculation process[1]. *Confidence: High.*
- "This MRI-based methodology has been approved by FERC and is being implemented over a series of Forward Capacity Auctions (FCAs)." **Partially accurate but outdated.** RCA/MRI proposed for FCA 19 (2026 auction, 2028-2029 delivery), to be filed with FERC by late 2025; not yet fully approved/implemented as of Apr 2026[1][4][5]. No FERC approval confirmed in results. *Confidence: Medium.*
- "For offshore wind, the initial capacity values for projects entering the queue are now determined using this probabilistic approach." **Inaccurate.** New offshore wind uses synthetic profiles via DNV process (Phase 1 of RCA), not yet fully probabilistic MRI for accreditation; proposed for FCA 19[1][7][9]. *Confidence: High.*
- "MRI captures **correlated performance**. The first gigawatt... high capacity credit... the tenth gigawatt... highly correlated... lower marginal reliability impact." **Accurate.** Explicit purpose of MRI to account for diminishing returns from correlation[1][2][6]. *Confidence: High.*
- "ISO New England's current methodology... is a transition to a fully probabilistic, Marginal Reliability Impact model. The specific values are not static; they are... re-run for future auctions." **Accurate.** RCA is transitional, model re-run iteratively[1][8][9]. *Confidence: High.*

#### gpt Claims
- "ISO New England typically reviews and updates its methodologies periodically." **Accurate.** Iterative updates via NEPOOL/stakeholder processes[1][8]. *Confidence: High.*
- No other specific claims; response defers. **N/A.**

#### grok Claims
- "ISO-NE historically uses a methodology tied to Effective Load Carrying Capability (ELCC), which assesses a resource’s contribution... by modeling its output during peak load conditions and high-risk periods." **Accurate.** RCA builds on ELCC[1][4][5]. *Confidence: High.*
- "For offshore wind, this would account for seasonal wind patterns, historical performance data (if available), and correlation with system demand." **Accurate.** Profiles incorporate these via historical/synthetic data[1][7][9]. *Confidence: High.*
- "Offshore wind... higher capacity factors, especially in the Northeast." **Accurate.** Pre-Research notes higher capacity factors vs. onshore, better winter performance[2][6]. *Confidence: Medium.*
- "ISO-NE might assign a higher capacity credit to offshore wind compared to onshore—potentially in the range of 30-40% of nameplate capacity—based on studies from similar regions like PJM or NYISO." **Unconfirmed statistic.** Pre-Research mentions early estimates 20-40% (Claude), but no ISO-NE specific confirmation; criticized for uniform wind treatment[2][6]. Not in search results. *Confidence: Low.*
- "many offshore projects in the New England (e.g., Vineyard Wind) are still ramping up and lack long-term operational history." **Accurate.** Limited history drives synthetic profiles[1][7]. *Confidence: Medium.*
- "ISO-NE’s grid is increasingly stressed by winter peaks due to electrification of heating and transportation. Offshore wind’s output often peaks in colder months." **Accurate.** Aligns with Pre-Research on winter performance[2][6]. *Confidence: Medium.*
- No confirmation of FERC approval or exact ISO-NE values. **N/A.**

#### claude Claims
- "ISO-NE has been transitioning... toward... 'marginal reliability impact' (MRI) or similar probabilistic framework." **Accurate.** RCA/MRI transition[1][4][5]. *Confidence: High.*
- "The region has limited operational history with large-scale offshore wind." **Accurate.** <5 years data uses blends/synthetics[1][7][9]. *Confidence: High.*
- "Offshore wind generation profiles differ significantly from onshore wind (typically higher capacity factors, different diurnal patterns)." **Accurate.** Pre-Research/advocacy notes[2][6]. *Confidence: Medium.*
- "There's correlation risk during winter peak events when multiple offshore facilities might see reduced output simultaneously." **Accurate.** MRI addresses this[1][2]. *Confidence: High.*
- "The methodology likely involves an Effective Load Carrying Capability (ELCC) approach or a variant... calculates what fraction of nameplate capacity can be reliably counted." **Accurate.** RCA/ELCC variant[1][4][5]. *Confidence: High.*
- "For offshore wind, early estimates have suggested ELCC values in the range of 20-40% of nameplate." **Partially accurate.** Matches Pre-Research early estimates, but no firm ISO-NE values; uniform treatment criticized[2][6]. *Confidence: Medium.*
- "Proposed for FCA 19 (2026 auction, procuring for 2028-2029 delivery year), with a one-year delay option. Filed with FERC by late 2025" [from Pre-Research, echoed]. **Accurate.** Exact match[1][4][5]. *Confidence: High.*

### 2. Mapping Contradictions Between Models

| Contradiction | Models Involved | Correct Version | Reason and Citation |
|---------------|-----------------|-----------------|---------------------|
| FERC approval status of MRI/RCA | gemini: "approved by FERC and... implemented over FCAs." | Incorrect (gemini). Others defer/avoid claim. | RCA proposed for FCA 19, FERC filing by late 2025; no approval confirmed as of Apr 2026[1][4][5]. Pre-Research stable since Feb 2024, no recent change[8][9]. |
| Current application to offshore wind queues | gemini: "initial capacity values... now determined using this probabilistic approach." | Incorrect (gemini). grok/claude: historical/transitioning (accurate). | Synthetic DNV profiles for new offshore (Phase 1), full MRI for FCA 19 (2026+); not "now" implemented[1][7][9]. |
| Capacity value ranges | grok: "30-40%"; claude: "20-40%". | Neither fully confirmed; claude closer. | Early estimates 20-40%, but no official ISO-NE values; uniform wind treatment ongoing[2][6]. grok speculates from PJM/NYISO. |
| Implementation timeline | gemini: "over a series of FCAs" (vague). claude/Pre-Research: FCA 19 specific. | claude/Pre-Research correct. | Explicitly FCA 19 (2028-2029 delivery)[1][4][5]. |
| Legacy method details | gemini: peak hours performance. gr

---

## Synthesis
*Claude · incorporating all rounds*

ISO New England is in the process of transitioning its capacity accreditation methodology for offshore wind from a legacy empirical approach to a more sophisticated probabilistic framework called the Resource Capacity Accreditation (RCA). This new framework is based on Marginal Reliability Impact (MRI), which is conceptually similar to the Effective Load Carrying Capability (ELCC) used by other grid operators [VERIFIED][1][4][5].

- **Legacy Method**: Historically, ISO-NE determined the capacity value of renewables based on performance during peak hours. This method was criticized for not adequately capturing the diminishing returns of adding more intermittent resources to the grid.
- **MRI-Based Methodology**: The transition to MRI involves running thousands of simulations to predict how additional resources (like offshore wind) affect the overall system reliability. It calculates how much additional load the system can handle while maintaining a consistent level of reliability risk [VERIFIED][1][9].

- **Current Status**: The RCA initiative incorporating MRI is currently being phased in and has been proposed for implementation in the 2026 Forward Capacity Auction (FCA 19), with delivery projected for the 2028-2029 capacity year [VERIFIED][1][4][5]. Contrary to some reports, it has not yet received full FERC approval as of April 2026.
- **Offshore Wind Specifics**: Currently, the methodology for new offshore wind projects involves using synthetic profiles from a process developed with DNV, rather than a fully probabilistic MRI approach. The full incorporation of MRI for all resources, including offshore wind, is planned for future implementation [VERIFIED][1][7][9].

- **Higher Capacity Factors**: Offshore wind projects generally have higher capacity factors, especially in the Northeast, compared to onshore projects [LIKELY][2][6].
- **Time Sensitivity and Correlation**: MRI captures the correlated performance of similar resources, making capacity values dynamic and sensitive to factors like weather patterns and the existing fleet [VERIFIED][1][6].

The current transition reflects a significant methodological shift that aims to provide a more accurate and dynamic assessment of resource reliability contributions. While the method promises more adaptability, the lack of full implementation and FERC approval indicates ongoing refinement is needed. It is crucial for stakeholders to stay informed through updates from ISO-NE as methodologies evolve to meet regional decarbonization goals effectively.

1. **Monitor ISO-NE Updates**: Stay updated with ISO-NE's announcements and reports, especially regarding RCA progress and changes to capacity accreditation processes.
2. **Engage with Stakeholder Processes**: Participate in NEPOOL stakeholder meetings to gain insights and influence the development of these methodologies.
3. **Review FERC Filings**: Keep an eye on FERC filings related to these methodologies to understand any regulatory changes that may impact implementation timelines and resource planning.

This response incorporates current, verified insights from live research, contrasting misinformation found in some round-1 models.

---

*Generated by ai-roundtable*
*Putting the best frontier minds to work.*
*github.com/JSTcurious/ai-roundtable*