`t9302-fast-filter.sh` has example usage of all the programs in this
directory.  However, for convenience...

The scripts in this directory can be run as follows:

1. Common setup

        $ MYPATH=$(basename /PATH/TO/DIR/CONTAINING/git_fast_filter.py)
        $ export PYTHONPATH=$MYPATH:$PYTHONPATH

2. Running the individual scripts:

  If `SCRIPT_NAME` is one of `commit_info.py`, `file_filter.py`,
  `rename_master_to_slave.py`, or `strip-cvs-keywords.py`:

        $ mkdir target_dir
        $ cd target_dir
        $ git init
        $ (cd source_repo && git fast-export --all) | $SCRIPT_NAME | git fast-import

  `print_progress.py`:

        $ print_progress.py source_repo target_nonexistent_dir

  `create_fast_export_output.py`:

        $ create_fast_export_output.py

  `splice_repos.py` can only be used on very specific repositories; see
  `t9302-fast-filter.sh` for details.

  `collab` accepts a range of options; just run

        $ collab

  to get a help message.
