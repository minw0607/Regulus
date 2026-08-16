# The Regulus Relation Algebra

**Status:** design foundation. No code implements this yet — it is written first,
deliberately, because the crosswalk table is the asset the whole system rests on
and its semantics have never been stated. Implementation (the composition filter
and the signature audit) follows only after this is agreed.

**See also** [`theory.md`](theory.md), which formalises the surrounding framework
and surveys the literature. Two corrections from that review are folded in below:
the constraints are **inclusions, not equations** (§2), and confidence must be a
**semiring annotation, not per-rule penalties** (§7) — the latter fixes a genuine
non-confluence in the first draft.

---

## 1. The defect this addresses

`graph_expand` currently walks **any** `CROSSWALK` edge, in **either** direction,
and composes relation types **blindly**. Nothing checks whether following a
`related` edge and then another `related` edge yields anything meaningful, or
whether traversing a `mitigates` edge backwards means what the forward direction
meant.

This is not hypothetical. Measured on the current corpus:

| | count |
|---|---|
| `mitigates` edges | 246, over 35 mitigations and 75 techniques |
| busiest mitigation | `AML.M0024` covers 17 techniques |
| busiest technique | `AML.T0053` has 11 mitigations |
| **2-hop mitigation↔mitigation pairs via a shared technique** | **858** |
| **2-hop technique↔technique pairs via a shared mitigation** | **1,898** |

So roughly **2,750 two-hop connections exist purely because two nodes happen to
share a popular neighbour** — the classic hub effect. Against that, the entire
cross-framework web that makes GraphRAG worthwhile is **36 edges** (35 `related`
+ 1 `equivalent`). Untyped expansion drowns the signal in hub noise.

Two provisions sharing a control are not thereby related, and saying so in a
governance report would be an unforced error.

---

## 2. Formal model

The knowledge network is a **typed quiver** `Q`:

- **vertices** — provisions (plus `Framework` and `RiskCategory` nodes, which do
  not participate in this algebra);
- **arrows** — the relation types, which are the **generators**;
- **paths** — the free category on `Q`: every finite chain of composable arrows.

Multi-hop retrieval walks paths. But the free category admits *every* chain,
including meaningless ones, so we constrain it.

**Correction to the first draft.** That draft wrote `𝒜 = free category / I` with
`I` an ideal. That is wrong: an ideal imposes **equations** `r ; s = t`, whereas
§8 asserts **inclusions**

```
        r ; s  ⊑  t
```

— every pair related by the composite is *also* related by `t`, not conversely.
So the object is not a quotient algebra but a **set of role inclusion axioms** over
a relation algebra, which is exactly the form standardised as OWL 2 / SROIQ
*complex role inclusion axioms*. §8 is that axiom set.

Correspondingly the data is a lax functor into **`Rel`** (sets and binary
relations), not `Set`: our arrows are many-to-many, so they are relations, not
functions. See `theory.md` §2 for the precise statement — it is what gives the
audit in §12 its meaning as a soundness check.

We borrow the presentation *language* only. There is no learned operator here, and
no claim that the classification theory of quiver representations applies (our
graph is nothing like a Dynkin diagram, and we are not embedding it).

---

## 3. Sorts

Composition validity depends on what kind of thing each provision is:

| Sort | Meaning | Members |
|---|---|---|
| `Req` | a normative requirement | EU AI Act articles, NIST RMF subcategories, NIST 600-1 action groups, OECD principles, ISO clauses |
| `Risk` | a named risk / vulnerability class | OWASP Top 10 for LLM entries |
| `Tech` | an adversarial technique | ATLAS `AML.T*` |
| `Mit` | a control that reduces a technique's risk | ATLAS `AML.M*` |

Sorts are derivable from `framework_id` and provision-id prefix; nothing new needs
to be curated.

---

## 4. Relation inventory (as it stands today)

| Relation | Edges | Where it lives | Provenance |
|---|--:|---|---|
| `mitigates` | 246 | ATLAS → ATLAS | authoritative (ships in ATLAS data) |
| `specializes` | 69 | ATLAS → ATLAS | authoritative (ATLAS hierarchy) |
| `supports` | 49 | NIST 600-1 → NIST RMF | authoritative (600-1 keys to RMF subcategories) |
| `related` | 35 | 8 different cross-framework pairs | curated |
| `equivalent` | 1 | OWASP → ATLAS | curated |

Note the shape: a **dense authoritative ATLAS core** (315 edges), a **NIST bridge**
(49), and a **thin curated cross-framework web** (36). The 36 edges are the ones
that produce the cross-framework reach we advertise, and they are the least
formalised. That asymmetry drives §11.

---

## 5. Declared semantics

For each generator: its signature, its intended meaning, and the algebraic
properties we *assert* it has. §12 makes every assertion measurable, so a false
assertion becomes a detectable defect rather than a silent one.

### `equivalent : X ↔ Y`
Two provisions denote **the same phenomenon**, possibly in different frameworks
and even different sorts (OWASP LLM01 `Risk` ≡ ATLAS T0051 `Tech` — one names a
vulnerability class, the other the attack that realises it).
- symmetric: **yes** · transitive: **yes**, with drift risk — cap at depth 2
- an equivalence relation in intent

### `related : X ↔ Y`
A **thematic correspondence** weaker than equivalence.
- symmetric: **yes** · transitive: **no** — this is the crucial one
- Non-transitivity is the point: A thematically like B, B thematically like C
  says nothing about A and C.

### `supports : Req → Req`
Source gives **implementation detail for** a more general target (NIST 600-1
GV-1.1 supports RMF GOVERN 1.1). A refinement relation.
- symmetric: **no** · transitive: **yes** (refinement chains compose)
- cardinality: many-to-one expected

### `mitigates : Mit → Tech`
Source is a **control that reduces the risk** of the target technique.
- symmetric: **no** · transitive: **no** (and ill-typed: the target is a `Tech`,
  which is never the source of a `mitigates` edge)
- cardinality: many-to-many

### `specializes : Tech → Tech`
Source is a **special case of** the target.
- symmetric: **no** · transitive: **yes** · antisymmetric and **acyclic** (a forest)
- cardinality: many-to-one

---

## 6. Converses, and a bug in the current graph

The graph is built with `nx.Graph()` — **undirected**. Traversal therefore follows
every edge in both directions, which for the three directional relations means we
are silently using the **converse** relation without labelling it as such:

| forward | converse | traversing backwards actually means |
|---|---|---|
| `equivalent` | `equivalent` | (self-converse — fine) |
| `related` | `related` | (self-converse — fine) |
| `supports` | `supported_by` | "is refined by" |
| `mitigates` | `mitigated_by` | "is mitigated by" |
| `specializes` | `generalizes` | "is generalised by" |

So the algebra has **8 directed labels**, not 5. The composition table must be
written over the 8, because — as §8 shows — `specializes ; mitigated_by` is sound
while `generalizes ; mitigated_by` is not, and an undirected walk cannot currently
tell them apart.

---

## 7. Confidence: a semiring annotation

Every edge carries a provenance string today. Map it to a weight:

| Provenance class | Example | `w` |
|---|---|--:|
| authoritative | ATLAS's own mitigation links; NIST 600-1 → RMF keying | 1.00 |
| textual | rationale quotes the provision's own words (Art 15(5) names "adversarial examples or model evasion") | 0.90 |
| curated thematic | "curated seed — verify" | 0.60 |

**Correction to the first draft.** That draft set *path confidence = product of
edge weights × the rule's penalty*, which is **not well defined**: the result
depends on the order the rules are applied. For
`A --equivalent--> B --equivalent--> C --mitigated_by--> D`, reducing left-first
gives `0.9` and right-first gives `1.0`; for `specializes;specializes;mitigated_by`,
`0.80` vs `0.64`. (Latent only — `max_hops = 2`, so length-3 paths do not yet
arise — but the algebra was ill-defined as written.)

**The fix** is to annotate in a commutative semiring `(K, ⊕, ⊗, 0, 1)`, following
provenance semirings (Green–Karvounarakis–Tannen) and their extension to regular
path queries:

- weight of a **path** = `⊗` of its edge weights — associative, so grouping is
  irrelevant and the non-confluence disappears **by construction**;
- weight of a **node reached by several paths** = `⊕` over those paths.

Default `K` = **min-times** `([0,1], min, ×)`: `⊗ = ×` conjoins along a path,
`⊕ = min` takes the *worst* derivation — the conservative choice appropriate to
governance. A path below a floor (proposed **0.40**) is suppressed; the floor is a
placeholder pending calibration.

Rule-specific penalties, if retained, are applied at the point of rule application
and aggregated across derivations by `⊕`, rather than one derivation being picked
arbitrarily. See `theory.md` §E1, including the homomorphism property that lets us
compute provenance once and specialise the numeric scheme afterwards.

---

## 8. The composition table (the role inclusion axioms)

Diagrammatic order: `r ; s` means *follow `r`, then `s`*. Each row asserts
`r ; s ⊑ result`.

> **Regularity.** Unrestricted role composition is undecidable; OWL 2 recovers
> decidability by requiring a strict partial order `≺` on roles under which every
> axiom has a permitted shape. Every rule below is of the form `S ∘ R ⊑ R` or
> `R ∘ R ⊑ R`, and the order
> `equivalent ≺ {related, supports, mitigated_by}`, `{specializes, related} ≺ mitigated_by`
> is acyclic — so **this table is `≺`-regular and therefore decidable**. Any new
> rule must preserve that property; see `theory.md` §E2.

| Composite | Result | Penalty | Justification |
|---|---|--:|---|
| `equivalent ; mitigated_by` | `mitigated_by` | 1.0 | Same phenomenon ⟹ the same controls apply. **This is the OWASP→ATLAS→control chain.** |
| `equivalent ; equivalent` | `equivalent` | 0.9 | Transitive, with drift; depth-capped |
| `equivalent ; related` | `related` | 0.9 | Weakest link |
| `equivalent ; supports` | `supports` | 0.9 | |
| `specializes ; mitigated_by` | `mitigated_by` | 0.8 | **Inheritance downward**: a control for the general technique applies to the specific case, though possibly incompletely |
| `specializes ; specializes` | `specializes` | 1.0 | Transitive taxonomy |
| `supports ; supports` | `supports` | 1.0 | Refinement chain |
| `related ; mitigated_by` | `mitigated_by` | 0.5 | Only defensible when the `related` edge is textually grounded — see §11 |
| `generalizes ; mitigated_by` | **⊥ suppress** | — | **Unsound direction.** A control for one narrow sub-technique need not cover the parent, which subsumes many other variants |
| `related ; related` | **⊥ suppress** | — | Thematic drift; `related` is not transitive |
| `mitigates ; mitigated_by` | **⊥ suppress** | — | Hub effect: two controls for the same technique are not thereby related (858 such pairs) |
| `mitigated_by ; mitigates` | **⊥ suppress** | — | Hub effect: two techniques sharing a control are not thereby related (1,898 such pairs) |
| anything ill-typed by §3 | **⊥ suppress** | — | Sort mismatch |

Everything not listed is suppressed by default: **the ideal is a whitelist.** For a
governance tool the safe default is to refuse to compose.

---

## 9. What a composed reach asserts

A 2-hop reach labelled `mitigated_by` at confidence 0.9 asserts exactly:

> *There exist two cited edges, `e₁` and `e₂`, whose composition is declared sound
> by rule R in §8; therefore the endpoint is reported as a candidate control for
> the seed provision, at the confidence implied by both edges' provenance.*

It does **not** assert that any standards body has stated the endpoint relationship
directly. Composed reaches must therefore always be rendered with their full path
and per-hop signals — never collapsed into a bare claim — which is what the
existing `evidence_paths` output already does.

---

## 10. Minimal generators

Is any generator redundant?

- `equivalent` ⊂ `related` semantically — but **not** removable: they compose
  differently (`equivalent` composes, `related` does not), and that distinction is
  the entire point of the table.
- `supports` vs `specializes` — different sorts (`Req→Req` vs `Tech→Tech`) and
  different meanings (refinement of guidance vs taxonomic subsumption). Both stay.
- `mitigates` is the only cross-sort control relation. Stays.

**Conclusion: the five generators are minimal — but `related` is overloaded, and
should be split.** See below.

---

## 11. Findings and proposed changes

**F1 — `related` is doing two different jobs.** Its 35 edges range from
*"Article 15(5) literally names 'adversarial examples or model evasion'"* — a
textual finding — down to *"ISO planning corresponds to EU risk management"* — a
loose theme. Only the first kind can defensibly compose. The flagship
`EU Art 15 → Craft Adversarial Data → Model Hardening` chain relies on a `related`
edge of the first kind.

> **Proposal:** split into `addresses` (textually grounded: the provision's own
> words name the phenomenon; composes at penalty 0.9) and `related` (thematic;
> never composes). Reclassifying 35 edges is an afternoon of curation.

**F2 — `equivalent` is under-used.** One edge, when several OWASP↔ATLAS pairs in
`security_crosswalks.csv` are labelled `related` but plainly meet the equivalence
bar. Promoting them unlocks the strongest composition rule.

**F3 — direction is currently lost.** §6. Fixing this needs either a directed
graph or a direction flag consulted during traversal.

**F4 — hub suppression is the single highest-value rule**, by volume (§1).

---

## 12. The audit (item B), specified

For each relation type, measure — from the edge set alone, no embeddings, no
training — and compare against the declared expectation from §5:

| Invariant | Definition | Expectation |
|---|---|---|
| `sym_rate` | fraction of (u,v) with (v,u) also present, same relation | `equivalent`, `related` → 1.0; others → 0.0 |
| `tails_per_head` | mean distinct targets per source | `specializes` → ~1; `mitigates` → >1 |
| `heads_per_tail` | mean distinct sources per target | `supports`, `specializes` → >1 |
| `sort_signature` | observed (source sort, target sort) pairs | must match §3 |
| `acyclic` | is the relation's subgraph a DAG? | `specializes`, `supports` → yes |
| `cross_framework_rate` | fraction of edges crossing frameworks | `mitigates`, `specializes` → 0; `related` → 1 |
| `provenance_class` | distribution over §7 classes | every edge classifiable |

**Any mismatch is a data defect to fix, not a statistic to report.** That is the
discipline worth borrowing from the KGE literature: a relation is granted its
algebraic properties *because they were measured*, and the same measurement audits
the grant.

---

## 13. Non-claims

- No learned relation operators, no embedding of the graph, no link prediction.
  The composition table **derives nothing that was not asserted by a human** — it
  only decides which chains of existing citations may be shown together.
- The confidence weights of §7 are ordinal bookkeeping, not probabilities. They
  must not be presented as such until calibrated against a labelled set.
- Borrowing the quiver/presentation vocabulary is a matter of precision, not a
  claim to results from representation theory.
