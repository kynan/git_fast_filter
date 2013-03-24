`git_fast_filter.py` is designed to make it easy to rewrite the history of a
git repository.  As such it plays a similar role to git-filter-branch, and
was created primarily to overcome the (sometimes severe) speed shortcomings
of `git-filter-branch`. The idea of `git_fast_filter.py` is to serve as a
small library which makes it easy to write python scripts that filter the
output of `git-fast-export`. Thus, the calling convention is typically of
the form:

    git fast-export | filter_script.py | git fast-import

Though to be more precise, one would probably run this as

    $ mkdir target && cd target && git init
    $ (cd /PATH/LEADING/TO/source && git fast-export --branches --tags) \
        | /PATH/TO/filter_script.py | git fast-import

Example filter scripts can be found in the testcases subdirectory,
with a brief README file explaining calling syntax for the scripts.

# Abilities

`git_fast_filter.py` can be used to
  * modify repositories in ways similar to git-filter-branch
  * facilitate the creation of fast-export-like output on some set of data
  * splice together independent repositories (interleaving commits from
    separate repositories)

It has been used to modify file contents, filter out files based on content
and based on name; drop, split, and insert commits; edit author and
committer information; clean up commit log messages (and store excessive
information in git-note format); modify branch names; drop and insert blobs
(i.e. files) and/or commits, splicing together independent repositories
(interleaving commits), and perhaps other small changes I'm forgetting at
the moment.

There is also a `filtered_sparse_shallow_clone.py` library that can be used
to create scripts for creating a filtered sparse or shallow "clone" of a
repository, and for bidirectional collaboration between the filtered and
unfiltered repositories.

# Caveats

I think `git_fast_filter.py` works pretty well, but there are some potential
gotchas if you're not using recent enough versions of git or try to do
something unusual...

You need to be using git>=1.6.3 (technically, git >= v1.6.2.1-353-gebeec7d)
in order for filtering on a subset of history not including a root commit
to work correctly.  (In other words, if you're passing something like
`master~5..master` to `git-fast-export`, you need a recent version of git. If
you just pass `master` or `--all`, then old versions of git will suffice.)

You either need to use git>=1.6.2 or pass the `--topo-order` flag to
`git-fast-export` in order to avoid merge commits being squashed.
`git_fast_filter` passes this flag to `git-fast-export`, if you have it call
`git-fast-export` for you.

Since `git-fast-export` and `git_fast_filter.py` both work by assigning integer
identifiers to every blob and commit (and typically in the range 1..n), it
presents a uniqueness challenge when interleaving commits from separate
repositories or inserting commits or using the `--import-marks` flag.  In
particular, doing one of these things (interleaving commits from separate
repositories, inserting commits, or using the `--import-marks` flag) and not
letting git_fast_filter.py know about it is a recipe for trouble.  When
interleaving commits, make use of the `fast_export_output()` function instead
of piping git fast-export output to the script.  When using the
`--import-marks` flag to `git-fast-export`, again do so via the
`fast_export_output()` function so `git_filter_branch.py` can be aware of the
range of ids to avoid.

While `git_fast_filter` has some logic to keep identifiers unique when
inserting commits, using `--import-marks`, or splicing together commits from
separate repositories (which it does by remapping identifiers as
necessary), it may not handle corner cases.  Its identifier remapping has
been tested on special cases individually, but it has not been tested on
all combinations of special cases.  In particular, I do not know if it will
handle the combination of `--import-marks` being passed to multiple
`fast_export_output()` streams and trying to combine all these streams into a
single repository.  (Incidentally, I can't think of a use case for doing
that either.)

Inserting manually created commits (or interleaving commits between
repositories) provides an interesting challenge for `git_fast_filter`.
First, if you are inserting changes to files and expecting them to
propagate, you will be disappointed; each commit specifies the exact
version of each file (which is different from its first parent) that it
will use.  Thus, if you want to insert changes to files, you either have to
rewrite all subsequent files or use a different tool like git rebase.
Second, if the commits you insert end up on a merged branch (that is, the
inserted commit is reachable through the second or later parent of some
commit) then any new files you inserted would normally be dropped by
`git-fast-import`.  The reason for this is that `git-fast-import` expects each
commit to provide the list of files which are different than its first
parent.  Files must be repeated in the merge commit if they exist only on
the branches corresponding to parents after the first, even if these files
are not being changed in the merge commit.  `git_fast_filter.py` has some
ugly hacks to make this happen behind the scenes for you, but it only works
when the inserted commits contain new, unique files that are not also
created or modified on other branches.  If you do something clever or more
complicated than this that defeats my simple hack, we may need to modify
`git-fast-import` (and perhaps `git-fast-export`) to have them allow the
following behavior via some flag: diff relative to all parents and only
require merge commits to list files that conflict among the different
parents (or that were otherwise changed in the merge commit).

# Comparing/contrasting to git-filter-branch

* Similar Basics: The basic abilities and warnings in the first three
  paragraphs of the `git-filter-branch` manpage are equally applicable to
  `git_fast_filter.py`, except that *rev-list* options are passed to
  `git-fast-export` (which, as noted above, is typically executed separately
  in addition to the filter script).  In other words, the tools are very
  similar in purpose.

* Speed of Execution: By virtue of using fast-export and fast-import,
  `git_fast_filter` avoids lots of forks (typically thousands or millions of
  them) and bypasses the need to rewrite the same file 50,000 times.
  (Also, `git_fast_filter` does not use a temporary directory of any sort,
  and moving repositories to tmpfs to accelerate I/O would not
  significantly speed up the operation.)

* Speed of Development: Since usage of `git_fast_filter` involves writing a
  separate python script and typically invoking two extra programs, it
  takes longer to invoke than typing `git-filter-branch` one-liners.  (One
  can have the python script invoke fast-export and fast-import rather than
  doing it on the command line and using pipes, if one wants to.  It's
  still a little bit of extra typing, though.)  Speed of "development" is
  probably more important than speed of execution for many small
  repositories or simple rewrites, thus `git-filter-branch` will likely
  remain the preferred tool of choice in many cases.

* Location of rewritten History: `git-filter-branch` always puts the
  rewritten history back into the same repository that holds the original
  history.  That confuses a lot of people; while the same can be done
  with `git_fast_filter`, examples are geared at writing the new history
  into a different repository.

* Rewritting a subset of history (potential gotcha): When `git-fast-export`
  operates on a subset of history that does not include a root commit, it
  truncates history before the first exported commits.  This makes sense
  since the destination repository may not have the unexported commits
  already.  (Note that one can use the `--import-marks` feature to
  `git-fast-export` to notify fast-export that the destination repository
  does indeed have the needed commits, i.e. that an 'incremental' export is
  being done and thus that history should not be truncated.)  WHY THIS
  MATTERS: `git-filter-branch` will not truncate history when dealing with a
  subset of history, since it is writing the modified history back to the
  source repository where it is known that the non-rewritten commits are
  available.  If someone tries to duplicate such behavior with
  `git_fast_filter`, they may be surprised unless they pass the
  `--import-marks` flag to `git-fast-export`.
