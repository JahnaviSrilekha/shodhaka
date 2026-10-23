# Shodhaka review UI

React 19 + TypeScript + Vite. No UI framework, no router, no state library: the app is small
enough that plain React, a typed API module and a few hooks keep it easy to read.

```
src/
  api/types.ts        the report and review contract (mirrors src/shodhaka)
  api/client.ts       the only module that calls fetch(); throws ApiError with the server's message
  domain/review.ts    pure review rules: approve/reject options, review order, filters, fix insertion
  domain/packForm.ts  rule pack <-> editor form conversion (tested round trip)
  hooks/              useAnalysis (load, poll while Decider runs, optimistic review saves),
                      useLoad, useHashRoute (#/o/<org>/p/<project>/a/<analysis>...), useHotkeys, useToast
  components/         presentational pieces: StatusBadge, ConfidenceMeter, Breadcrumbs, Icon,
                      AppHeader (organization and project switchers)
  features/orgs/      register organizations; organization page with projects and general packs
  features/projects/  project page: new analysis, analyses, rules in effect and their source, packs
  features/packs/     pack list (upload YAML, template, on/off per project) and the Form | YAML editor
  features/upload/    the document drop zone
  features/analysis/  documents | findings | detail, with the human decision (ReviewPanel)
  features/editor/    edit the extracted text, insert a reviewed fix, save and re-check
```

Patterns used:
- **Feature folders**: each screen owns its components; shared pieces live in `components/`.
- **API layer + typed contract**: components never build URLs or parse responses; everything below an
  organization is addressed through a `Scope` ({org, project}), so a page can only reach its own project.
- **Pure domain module**: the review rules are plain functions with unit tests, not hidden in JSX.
- **Container / presentational split**: pages own data and side effects; list rows, badges and
  meters only render props.
- **Custom hooks for side effects**: polling, keyboard shortcuts, toasts.
- **Reducer for filter state** (`features/analysis/filters.ts`).
- **Optimistic updates with rollback** for review decisions.

```bash
npm install
npm run dev      # http://127.0.0.1:5173, forwards /api to shodhaka serve on :8000
npm test         # vitest + Testing Library
npm run build    # writes dist/, which shodhaka serve hosts on :8000
```
