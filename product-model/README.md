# Product Model

This directory is the **Product Model** of this repository, kept with
pdd-kit for Product-Driven Development (PDD): who the product serves, where
they reach it, what it keeps, what it can do, and which rules must stay true. It
is plain Markdown tracked in Git, and it is the source of truth for the intended
product definition.

## If you are an agent working in this repository

- **To implement it**, all of it or a part, work the way you and the user
  normally do. The model is the acceptance contract: see *What the code must
  honor* below. When you finish, recommend checking the code against the model
  with the `pdd-verify` skill; do not run the check unless asked.
- If the repository's agent instructions or the request say "Implement with
  pdd-verify: plan the work from `product-model/` in phases and check each
  part before the next.", or the installed `pdd-verify` skill says this
  install orchestrates implementation, implement with `pdd-verify` instead,
  unless the request says to implement without it.
- **To check the code against it**, use `pdd-verify`. **To change
  what the product should do**, use `pdd-ideate`. To model established
  code the model does not cover, use `pdd-map`.
- If those skills are not installed, run `npx pdd-toolkit install`.
- Do not edit this directory while implementing. If the model is ambiguous or
  seems wrong, stop and ask; never settle a product question in code.
- Never edit `cache/`. Run `npx pdd-toolkit lint` for structural checks.

## What the code must honor

- Capability Scenarios are acceptance tests for one Capability; Journey
  Scenarios are end-to-end tests across Capabilities.
- Business Rules must stay true. A Rule's `permits` names exactly who may
  perform an operation; everyone else is refused.
- A Screen's `shows` and `collects` are the facts it presents and the input
  it takes, not its layout or design.
- `availability` names the Interfaces and Experiences where behavior must
  work.
- An Entity's facts and states are what the product keeps and distinguishes,
  not a storage schema.
- A Variation's `selectedWhen` says what chooses each supported alternative.

## What it does not prescribe

- The stack and architecture: choose them yourself.
- Domains group the model by subject; they are not modules or services.
- References are navigation and context. They never prove the code matches and
  never prescribe a design.
- `coverage.md` says which of the repository's code the model accounts for,
  never whether that code matches it; it stays empty until code is mapped.

## Reading order

Start with `product.md` or `product/product.md`, then Entities, Interfaces
with their Experiences and Screens, Domains, Capabilities and their Scenarios,
Business Rules, Journeys and their Scenarios, and Variations. A resource is
`<id>.md`, or `<id>/<type>.md` when it owns child resources or assets.

Documentation: https://pdd-kit.dev
