# Mathematical Foundations of the Regulus Knowledge Network

**Status:** theory document. Part I formalises what is *already built*. Part II
proposes extensions, each with a stated formal basis and a concrete implementation
consequence. Part III surveys existing work — several of our ideas turn out to have
published, standardised forms, which is good news: it means we can adopt rather
than invent. Part IV states honestly what would remain novel.

Companion: [`relation-algebra.md`](relation-algebra.md) holds the composition
table itself.

---

# Part I — The current framework, formalised

## 1. Sorts and the provision set

Let `P` be the finite set of provisions, partitioned by a sort map
`τ : P → {Req, Risk, Tech, Mit}` (§3 of the companion doc). Write
`P_X = τ⁻¹(X)`.

Each `p ∈ P` carries immutable attributes: `text(p)`, `cite(p)`, `url(p)`,
`framework(p)`.

## 2. The schema is a finitely presented category

Following Spivak's formulation of database schemas [S12], a **schema** is a
finitely presented category: a directed multigraph (a quiver) together with path
constraints.

Our schema `𝒮`:

- **objects** — the four sorts;
- **generating arrows** — the relation types, with signatures
  ```
  supports    : Req  → Req        specializes : Tech → Tech
  mitigates   : Mit  → Tech       equivalent  : X ↔ Y      related : X ↔ Y
  ```
- **path constraints** — the composition table.

Two refinements over the companion doc, both of which matter:

**(a) The constraints are inclusions, not equations.** Yesterday's draft called
the constraint set an *ideal* `I` and wrote `kQ/I`. That is not accurate: an ideal
imposes *equations* `r;s = t`. What the table actually asserts is
`r ; s ⊑ t` — every pair related by the composite is *also* related by `t`, not
conversely. So the correct object is not a quotient algebra but a **set of role
inclusion axioms** over a relation algebra. This is exactly the form standardised
as OWL 2 / SROIQ **complex role inclusion axioms** [H06, W3C]. Corrected in §E2.

**(b) The target category is `Rel`, not `Set`.** A Spivak instance is a functor
`I : 𝒮 → Set`, i.e. every arrow is a *function*. Our arrows are many-to-many:
`mitigates` is a relation. The right target is therefore **`Rel`** — sets and
binary relations, which is the Kleisli category of the powerset monad on `Set`.

> **Definition 1 (instance).** An instance of `𝒮` is a lax functor
> `I : 𝒮 → Rel` assigning to each sort `X` the set `P_X`, and to each generator
> `r : X → Y` a relation `I(r) ⊆ P_X × P_Y`, subject to the inclusions
> `I(r) ; I(s) ⊆ I(t)` for each declared rule `r ; s ⊑ t`.

Laxity is precisely the inclusion-not-equation point. **The audit specified in
§12 of the companion doc is exactly the test that our data satisfies Definition 1.**
That gives the audit a formal meaning it previously lacked: it is a soundness
check on the instance, not a collection of descriptive statistics.

## 3. The relation algebra

Over `Rel` we have the classical Tarskian operations: composition `;`, converse
`˘`, union, and identity. Our graph is stored undirected, so traversal implicitly
uses `˘`, giving eight directed labels from five generators (companion §6). Write
`Λ` for that eight-letter alphabet.

## 4. Retrieval, formalised

The pipeline is the composite of three maps. **Nothing here is learned by us.**

**Stage 1 — metric seeding.** With `φ` a frozen pretrained encoder and
`v_p = φ(text(p))/‖·‖`:

```
σ_s(p) = ⟨φ(s)/‖φ(s)‖ , v_p⟩            Seed_k(s) = top-k of σ_s over the indexed subset
```

The indexed subset excludes stoplisted provisions and applies the layer quota. This
stage is **purely metric**: no relation is involved, and the graph is not consulted.

**Stage 2 — bounded path query.** Let `L ⊆ Λ*` be the language of admissible
paths: all single letters, plus exactly those two-letter words whitelisted by the
composition table. `L` is finite, hence regular.

> **Definition 2 (expansion).** `Reach(s) = { q : ∃ p ∈ Seed_k(s), ∃ w ∈ L, (p,q) ∈ I(w) }`

This is a **regular path query** (RPQ) in the graph-database sense [B13], under
arbitrary-path semantics, over a finite path language. Naming it matters: RPQ
evaluation under arbitrary-path semantics is tractable (unlike simple-path or
trail semantics, which are hard) — so our design sits on the right side of a known
complexity boundary, and the choice was accidental rather than reasoned.

**Stage 3 — ranking.** On the neighbourhood subgraph with column-stochastic
adjacency `Π`:

```
π = (1−α)(𝟙 − αΠ)⁻¹ e_s                        personalised PageRank
priority(p) = σ_s(p)·(1 + lev(p)) + π(p)        lev = frameworks reached + co-risk findings
```

This is the only genuine linear algebra in the system, and it operates on a
**known** adjacency matrix, not a fitted one.

## 5. The RAG / agent layer, formalised

Let `G_s` be the annotated subgraph returned by Stage 2 — nodes carrying
`(cite, text)`, edges carrying `(relation, rationale, source)`.

> **Definition 3.** The generation step is a map `R : G_s × Text → Text`
> implemented by a language model, constrained to the sub-language of strings
> whose provision citations all appear in `G_s`.

Two consequences worth stating precisely, because they are the architecture's
whole justification:

- **Groundedness is checkable.** Since `R`'s admissible output is defined relative
  to `G_s`, verifying an answer is a containment test on citations — decidable, and
  cheap. (We do not yet perform it; see the open abstention/verification item.)
- **The deterministic core is `R`-independent.** Stages 1–3 do not call `R`, so
  risks, provisions, priority and reach are invariant under any change of language
  model. This is what the reproducibility hash actually certifies.

## 6. What the framework is not

- No learned relation operators; relations are extensional data, not functions.
- No embedding of the graph. `φ` embeds *text* and was fitted on a general corpus,
  never on our edges. Deleting every edge leaves `φ` unchanged.
- The word "geometric" in GKN refers to a metric space used for *seeding only*.
  It does not denote relation geometry in the sense of the KGE literature.

---

# Part II — Proposed extensions

Each item: formal basis → what changes in code → why it is worth doing.

## E1. Semiring provenance for the confidence algebra  *(highest value)*

**The defect.** The companion doc attaches a multiplicative penalty to each
composition rule. That makes path confidence depend on the order rules are
applied. Concretely, for `A --equivalent--> B --equivalent--> C --mitigated_by--> D`:

```
(equiv;equiv);mitigated_by → 0.9 × 1.0 = 0.90
equiv;(equiv;mitigated_by) → 1.0 × 1.0 = 1.00
```

and for `specializes;specializes;mitigated_by`, `0.80` vs `0.64`. The confidence is
**not well defined**. (Latent only: `max_hops = 2` today, so length-3 paths do not
yet arise.)

**The fix, from the literature.** Green, Karvounarakis and Tannen's *provenance
semirings* [GKT07] annotate each base fact with an element of a commutative
semiring `(K, ⊕, ⊗, 0, 1)` and propagate: `⊗` combines along a derivation (joins),
`⊕` combines *alternative* derivations (unions). Ramusat et al. develop this
specifically for **regular path queries** [RSS20, R21] — our exact setting.

> **Proposal.** Annotate each *edge* with `w(e) ∈ K`; the weight of a path is
> `⊗` of its edge weights; the weight of a node reached by several paths is `⊕`
> over those paths.
>
> Since `⊗` is associative by the semiring axioms, **path weight is independent of
> grouping — the non-confluence disappears by construction**, not by convention.

Rule-specific penalties, if we keep them, attach at rule application and different
derivations of the same endpoint are then aggregated by `⊕` rather than one being
picked arbitrarily. Choice of `K` sets the reading:

| `K` | `⊕` | `⊗` | reading |
|---|---|---|---|
| Viterbi `([0,1], max, ×)` | best derivation | conjunction along path | optimistic |
| **min-times `([0,1], min, ×)`** | **worst derivation** | conjunction | **conservative — governance default** |
| provenance polynomials `ℕ[X]` | formal sum | formal product | full derivation history |
| tropical `(ℝ⁺∪∞, min, +)` | cheapest | additive cost | shortest-path |

**The theorem that makes this pay.** Query evaluation commutes with semiring
homomorphisms [GKT07]: evaluate **once** in the universal semiring `ℕ[X]`, then
specialise to any concrete confidence scheme by a homomorphism, without re-running
the query.

**And an observation about what we already built:** our `evidence_paths` output —
the chain with a signal at every hop — *is* the provenance polynomial rendered for
humans, and our confidence number is its image under a homomorphism to a numeric
semiring. We arrived at the right object informally; this names it and tells us how
to compute it once and reuse it.

**Code consequence.** Replace per-rule penalty multiplication with an edge
annotation + `⊗`/`⊕` fold; make the semiring a parameter (default: min-times).
`GraphReach.signals` becomes the polynomial term. ~1 day.

## E2. Regularity — and a decidability guarantee we already satisfy

**The risk.** Unrestricted role composition is **undecidable** [H06]. OWL 2 avoids
this with a *regularity restriction*: there must exist a strict partial order `≺`
on roles such that every inclusion has one of the permitted shapes, notably
`R∘R ⊑ R`, or `S₁∘…∘Sₙ∘R ⊑ R` / `R∘S₁∘…∘Sₙ ⊑ R` with every `Sᵢ ≺ R`.

**Checking our table.** Every rule in the companion §8 has the shape `S ∘ R ⊑ R`
or `R ∘ R ⊑ R`. Take

```
equivalent ≺ related,  equivalent ≺ supports,  equivalent ≺ mitigated_by,
specializes ≺ mitigated_by,  related ≺ mitigated_by
```

This is acyclic (`equivalent` is minimal; `mitigated_by` maximal), hence a strict
partial order, and each rule satisfies the corresponding condition. The
transitivity rules `r∘r ⊑ r` are permitted unconditionally.

> **Claim.** The Regulus composition table is `≺`-regular, therefore expressible
> as a SROIQ role hierarchy, therefore decidable.

That is a real guarantee about the design, obtained for free — and it converts to
an **acceptance test**: any newly proposed rule must preserve regularity. Roughly
30 lines to check mechanically, and it prevents someone later adding a rule that
silently makes the rule set non-terminating.

## E3. The audit as a functor-condition check

Definition 1 gives §12 of the companion doc its meaning: each declared property
(symmetry, transitivity, sort signature, acyclicity) is a condition on the instance
`I`, and the audit decides whether `I` satisfies it. A failure is a **data defect**,
not a statistic. Report it as: *rule `r;s ⊑ t` is violated by N edge pairs — here
they are.*

## E4. Sort-level reachability

The sort quiver has 4 objects and 8 directed arrows. Compute the reachability
relation on sorts under the admissible language `L`. This answers, a priori: *which
sorts can reach which, in how many hops, through which bridge relation?* We already
know the answer will show `Req ⇝ Mit` requires crossing into `Tech` via one of
**36** cross-framework edges — quantifying exactly where curation is thin. A 4×4
matrix; an hour.

## E5. Radical filtration = hop layers  *(justification only)*

For the projective `P_p = e_p·𝒜` (all admissible paths out of `p`), the radical
filtration `rad^n P / rad^{n+1} P` is exactly "reachable in exactly *n* hops". So
hop-stratified ranking is the canonical filtration rather than an arbitrary choice.
One sentence of justification; no code.

## Explicitly out of scope

- **Ext¹/Ext² for minimal generators and relations.** Correct tool when an algebra
  is too big to inspect; ours has four objects and is visible by reading.
- **Gabriel's theorem, indecomposable decomposition.** We are in wild
  representation type; there is no classification to obtain.
- **Projective presentations of retrieval results.** A scored set is not a module;
  there is no natural action. Forcing one would be notation without content.
- **Learned relation operators (KGE).** Rejected on governance grounds
  (uncited inferred edges) and on data grounds (475 nodes / 400 edges).

---

# Part III — Related work

**Provenance semirings.** Green, Karvounarakis & Tannen, *Provenance Semirings*,
PODS 2007 [GKT07] — the foundational result that bag semantics, probability,
trust and why-provenance are instances of one semiring computation, and that
evaluation commutes with semiring homomorphisms.
· <https://web.cs.ucdavis.edu/~green/papers/pods07.pdf>
· Survey: <https://www.cis.upenn.edu/~val/15MayPODS.pdf>

**Provenance for path queries.** *Provenance for Regular Path Queries*
(arXiv:2001.09864) and Ramusat, *Provenance-Based Algorithms for Rich Queries over
Graph Databases*, EDBT 2021 — semiring provenance specialised to RPQs, i.e.
precisely our Stage 2.
· <https://arxiv.org/pdf/2001.09864> · <https://openproceedings.org/2021/conf/edbt/p16.pdf>

**Semiring provenance for description logics.** *Semiring Provenance for
Lightweight Description Logics* (arXiv:2310.16472) — bridges the provenance and DL
threads; relevant if we later formalise the table as a DL role hierarchy.
· <https://arxiv.org/pdf/2310.16472>

**Complex role inclusions / SROIQ.** Horrocks, Kutz & Sattler, *The Even More
Irresistible SROIQ*, KR 2006 [H06]; W3C OWL 2 Structural Specification (property
chain axioms, regularity restriction).
· <https://www.w3.org/TR/owl2-syntax/>

**Regular path queries.** Barceló, *Querying Graph Databases*, PODS 2013 [B13] —
RPQ/CRPQ semantics and the complexity separation between arbitrary-path (tractable)
and simple-path/trail (hard) semantics.
· <https://dl.acm.org/doi/pdf/10.1145/2463664.2465216>

**Categorical databases.** Spivak, *Functorial Data Migration* [S12] — schema as a
finitely presented category (graph + path equations), instance as a set-valued
functor, with `Δ/Σ/Π` migration functors.
· <https://arxiv.org/pdf/1009.1166>

**Quiver representations.** Standard theory: representations assign vector spaces
to vertices and linear maps to arrows; Gabriel's theorem ties finite representation
type to ADE Dynkin diagrams; minimal generators/relations correspond to `Ext¹`/`Ext²`.

**KGE and relation properties.** Nickel et al. (RESCAL, 2011) as the general
bilinear case; the ComplEx/RotatE line for symmetry/inversion/composition
expressiveness; Ruffinelli et al., ICLR 2020, on tuning dominating architecture.
Rule mining (AMIE, AnyBURL) is the empirical counterpart of finding multiplicative
identities among relations.

---

# Part IV — What would actually be novel

Being honest about this matters more than claiming credit.

**Not novel:** the semiring treatment of confidence (GKT07, standard); role
inclusion axioms (OWL 2, standardised); RPQ formalisation of traversal (textbook);
schema-as-category (Spivak). Every core formal move we would make is published.
**That is the good outcome** — it means we can cite rather than defend.

**Arguably novel, as an applied contribution:**

> **Provenance-obligatory inference.** An inferred edge is admissible *only if* its
> full derivation can be rendered as a chain of cited source spans; derivations
> that cannot be so rendered are suppressed rather than reported with low
> confidence.

Semiring provenance makes derivations *available*; DL role inclusions make
inference *sound*; neither makes rendering the derivation a **precondition of
reporting**. That inversion — provenance as an admissibility gate rather than an
explanatory add-on — is a governance-specific design stance, and combined with a
conservative `⊕ = min` it yields a system whose reported inferences are auditable
by construction.

That is an architecture and policy claim, not a theorem, and should be presented
as such. The defensible summary of this project's contribution remains: **curated
cited data, provenance discipline, and evaluation methodology** — now resting on
formal foundations that are properly named and attributed.
