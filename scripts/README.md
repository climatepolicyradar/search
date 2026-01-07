# Scripts for performing tasks on this codebase

This folder is structured as follows:

``` text
scripts
|__ folder1
|__ folder2
|__ ...
|__ ephemeral
```

To avoid accidental collection of tech debt/broken code:

- all scripts in this directory must be in subdirectories of `scripts/` (there's a CI rule that checks for this), and
- all scripts except for those in the `ephemeral/` dir must have end-to-end tests.
