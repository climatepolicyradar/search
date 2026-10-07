# Adding synonyms to the documents and passages query rules

We keep lists of synonyms/acronyms and their equivalents which are applied at
query time ('query rewrites'). For example, when a user searches `ev`, the vespa
would actually perform the query `ndc "nationally determined contribution"`
(adding "nationally determined contribution" to the query).

## Editing the synonym lists

The query rewrites are located in `vespa/app/rules`: `documents.sr`,
`labels.sr`, and `passages.sr`. The `sr` stands for 'semantic rules'. For the
purposes of adding synonyms, we only want to edit `documents.sr` and
`passages.sr`.

Since `passages.sr` inherits from `documents.sr`, we only need to edit
`documents.sr` as long as we want the to apply to both document and passage
search.

To add a new synonym, add a new line to `documents.sr` with the original term
(most likely an acronym) on the left side, followed by `+>`, and the
synonym/expanded acronym on the left side as `?"what acronym stands for";`. For
example:

```text
`ndc +> ?"nationally determined contribution";`
nature based solution -> ?"nature based solution" ?"nbs";
gga +> ?"global goal adaptation";
evs +> ?"electric car" ?"electric vehicle";
```

You may add multiple phrases on the right side but it is not generally advisable
to add conflicting definitions (for example if an acronym has two different
meanings). You must end each entry with `;`.

**_Important_**: you must make sure the right-hand side (the expanded forms) do
NOT contain any of the words in `vespa/app/lucene-linguistics/en/stopwords.txt`
as they are removed during indexing and therefore the rule won't match correctly
if you put them here. For example, `gga +> ?"global goal adaptation";` and not
`gga +> ?"global goal on adaptation";`

Commit the change. There is an automatic CI check that will tell you if and
where any stopwords were detected. When your branch is merged to main, the
change will be deployed to production search.
