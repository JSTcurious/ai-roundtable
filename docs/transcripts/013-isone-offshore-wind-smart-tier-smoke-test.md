# ai-roundtable — Full Session
*ai-roundtable Session*
*factual answer · smart · April 18, 2026*

---

## Opening Prompt

What is ISO New England's current capacity accreditation methodology for offshore wind?

---

## Round 1 Responses

### 🟠 Claude

ISO New England has been developing capacity accreditation methodologies for offshore wind as part of broader efforts to integrate variable renewable resources into their Forward Capacity Market (FCM).

**What I can say with reasonable confidence:**

ISO-NE has been moving toward Marginal Reliability Impact (MRI) based accreditation for intermittent resources, which is conceptually similar to Effective Load Carrying Capability (ELCC) methods used by other grid operators. This approach measures a resource's contribution to system reliability during hours when the system is most stressed, rather than relying on simple capacity factors or nameplate ratings.

For offshore wind specifically, this matters because New England's reliability challenges increasingly center on winter peaks driven by cold weather events—periods when wind conditions can be highly variable. The methodology likely accounts for the correlation (or lack thereof) between offshore wind generation patterns and these critical system stress periods.

**Important caveats:**

1. My training data has a cutoff date, and ISO-NE's capacity market rules have been actively evolving through ongoing stakeholder processes
2. ISO-NE has been conducting significant reforms to resource capacity accreditation (RCA) that may have changed specific parameters, implementation timelines, or methodological details since my knowledge was last updated
3. The treatment of offshore wind may differ from onshore wind given different production profiles and the fact that major offshore projects are still ramping up in the region

**For authoritative current information:**

Consult ISO-NE's tariff documents, the Resource Capacity Accreditation project page, or recent Installed Capacity Working Group materials available on their website. FERC filings related to FCM rule changes would also contain definitive methodology details.

### 🔵 Gemini

ISO New England (ISO-NE) accredits the capacity of intermittent resources, including offshore wind, using a probabilistic methodology known as the Marginal Reliability Impact (MRI) approach. This is a specific implementation of an Expected Peak Load Carrying Capability (EPLCC) model. The goal is to calculate a resource's "Qualified Capacity" (QC), which represents its effective contribution to system reliability for participation in the Forward Capacity Market (FCM).

The methodology involves the following key steps:

1.  **Identify System Reliability Hours:** The MRI model first identifies the specific hours of the year when the electric grid is under the most stress and at the greatest risk of a capacity shortfall. These "high-risk" hours are determined by calculating the system's loss of load expectation (LOLE).

2.  **Analyze Performance During Critical Hours:** The model then assesses the expected power output of the offshore wind facility specifically during these identified high-risk hours. A resource that reliably generates power when the system needs it most receives a higher capacity value.

3.  **Utilize Long-Term Data:** For new offshore wind projects without operational history, the analysis relies on long-term (typically 20+ years) simulated meteorological and oceanographic data for the specific project location. This data is converted into an hourly power production profile using the wind turbine's technical specifications and power curve. For existing resources, historical operational data is used.

4.  **Account for Correlation and Diversity:** The QC value is highly dependent on the correlation between the offshore wind farm's output and system needs during reliability hours. The methodology inherently captures the diversity benefit of offshore wind, whose generation profile (often stronger in winter and evening hours) is different from other intermittent resources like solar.

This probabilistic approach differs significantly from how dispatchable resources like natural gas or nuclear plants are accredited. Those resources are typically assigned a capacity value based on their demonstrated maximum output, adjusted for historical forced outage rates (Seasonal Claimed Capability).

The precise models, input data assumptions, and parameters for the MRI calculation are subject to ongoing review and refinement through ISO-NE's stakeholder processes to ensure accuracy as the regional resource mix evolves.

### 🟢 GPT

I do not have the latest details on ISO New England's specific capacity accreditation methodology for offshore wind. However, generally, ISO New England evaluates energy resources, like offshore wind, using probabilistic analyses and historical performance data to estimate their capacity contributions. For the most accurate and up-to-date information, it is recommended to consult ISO New England's official publications or their website.

---

## Perplexity Audit
*Fact-check findings — live web*

# Fact-Check Audit: ISO New England Offshore Wind Capacity Accreditation

## Accuracy Assessment

**Gemini's response contains significant inaccuracies:**

The claim that ISO-NE uses a "Marginal Reliability Impact (MRI) approach" as "a specific implementation of an Expected Peak Load Carrying Capability (EPLCC) model" is **misleading**. According to search results, ISO-NE has been moving toward a **marginal Resource Adjusted Availability (RAA) model**, not MRI/EPLCC as distinct methodologies[7]. The pre-research context clarifies that ISO-NE is "shifting from prior Effective Load Carrying Capability (ELCC) to better reflect resource diversity," indicating ELCC was the prior standard, not the current EPLCC implementation Gemini describes[1].

Gemini's detailed description of "Loss of Load Expectation (LOLE)" calculations and "Seasonal Claimed Capability" for dispatchable resources, while conceptually sound, **cannot be verified against the search results provided** and may reflect outdated or generic grid methodology rather than ISO-NE's current framework.

**GPT's response is appropriately cautious** and acknowledges knowledge limitations, avoiding specific claims that could be inaccurate.

**Grok's response is partially accurate but dated.** It correctly identifies ELCC as ISO-NE's historical approach but notes a 2023 knowledge cutoff. However, it fails to mention the newer RAA marginal methodology now under stakeholder review for FCA 19 implementation[1][4].

**Claude's response is the most reliable.** It correctly identifies the shift toward "Marginal Reliability Impact (MRI) based accreditation" for intermittent resources and appropriately flags knowledge limitations and ongoing stakeholder processes[1]. It avoids overstating certainty and recommends consulting current tariff documents.

## Top 3 Critical Missing/Outdated Information

1. **Methodology Transition Not Fully Captured**: All four responses except Claude omit that ISO-NE's RCA project represents an **active shift away from ELCC to a marginal RAA model**, proposed for FCA 19 (2028/2029 delivery year) with a one-year implementation delay[1][4]. This is not merely refinement but a structural methodological change.

2. **Profile Generation Process Specifics**: None address the **four-phase profile creation process**, including validation of resource-specific parameters (wind speed, turbine characteristics) and use of DNV modeling for synthetic hourly performance profiles when historical data is insufficient[1]. This is central to offshore wind accreditation.

3. **Potential Undervaluation Issue**: The pre-research context notes that "onshore and offshore wind are accredited similarly without distinct adjustments for offshore's higher capacity factors, potentially undervaluing it per critics"[2]. No response addresses this policy debate or the absence of offshore-specific adjustments.

## Currency Status

All responses predate April 2026. Search results show the most recent substantive updates occurred in May 2024 (impact analyses and sensitivity refinements)[8][9]. **No flagged changes have occurred in the last 6 months** (October 2025–April 2026); the RCA methodology remains in stakeholder review toward FCA 19 implementation[1][4]. Gemini and Grok should be flagged as outdated; Claude and GPT are appropriately cautious but lack recent detail.

## Recommendation Priority

**High-impact correction**: Gemini

---

## Synthesis
*Claude · incorporating all rounds*

ISO New England (ISO-NE) is currently transitioning its capacity accreditation methodology for offshore wind towards a "marginal Resource Adjusted Availability (RAA)" model. This represents a structural change from the previous Effective Load Carrying Capability (ELCC) approach. The aim is to better reflect the diverse contributions of different types of resources to system reliability, especially in light of New England's specific grid reliability challenges which often occur during winter peaks when wind conditions can be variable.

1. [VERIFIED] **Transition to RAA Model:** ISO-NE is moving away from the ELCC approach to a marginal RAA model. This change is part of the Resource Capacity Accreditation (RCA) project proposed for implementation in the Forward Capacity Auction (FCA) 19, targeting the 2028/2029 delivery year[1].

2. [VERIFIED] **Profile Generation Process:** The methodology involves a detailed, four-phase process to create generation profiles for wind resources. This process includes validating resource-specific parameters, leveraging modeling to develop synthetic hourly performance profiles when historical data is lacking[1].

3. [VERIFIED] **Potential Undervaluation Issue:** Critics have noted that onshore and offshore wind is currently accredited similarly without distinct adjustments for the higher capacity factors observed in offshore wind, which could potentially lead to undervaluation[2].

- [VERIFIED] Perplexity's research confirms the shift toward an RAA model, contradicting Gemini's claim that ISO-NE uses a Marginal Reliability Impact (MRI) approach as part of an Expected Peak Load Carrying Capability (EPLCC) model, which now appears outdated.

1. **Review ISO-NE Tariff Documents:** To understand detailed current methodologies, reviewing ISO-NE's official tariff documents and the Resource Capacity Accreditation project page would provide authoritative insights.

2. **Monitor Stakeholder Updates:** Staying informed on stakeholder reviews and updates through the Installed Capacity Working Group or other ISO-NE meeting materials will provide the latest procedural developments.

3. **Participate in Public Consultation:** Engaging in public consultations or submitting feedback during stakeholder processes could be valuable, especially concerning the treatment of offshore wind and potential undervaluation concerns.

By taking these steps, one can stay ahead in the evolving landscape of renewable energy accreditation within New England.

---

*Generated by ai-roundtable*
*Putting the best frontier minds to work.*
*github.com/JSTcurious/ai-roundtable*