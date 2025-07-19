import json
import os
import shutil

import click

from app.commands.check.git import git
from app.commands.check.github import github
from app.commands.progress.constants import (
    LOCAL_FOLDER_NAME,
    PROGRESS_REPOSITORY_NAME,
    STUDENT_PROGRESS_FORK_NAME,
)
from app.utils.click import error, info, success, warn
from app.utils.gh_cli import (
    clone_with_custom_name,
    fork,
    get_prs,
    get_username,
    has_fork,
    pull_request,
)
from app.utils.git_cli import add_all, add_remote, commit, push
from app.utils.gitmastery import (
    GITMASTERY_CONFIG_NAME,
    generate_cds_string,
    require_gitmastery_root,
)


@click.command()
@click.pass_context
def on(ctx: click.Context) -> None:
    """
    Enables sync between your local progress and remote progress.
    """
    verbose = ctx.obj["VERBOSE"]

    gitmastery_root_path, gitmastery_config = require_gitmastery_root(
        requires_root=True
    )

    ctx.invoke(git)
    ctx.invoke(github)

    info("Syncing progress tracker")
    info(
        f"Checking if you have fork of {click.style(PROGRESS_REPOSITORY_NAME, bold=True, italic=True)}"
    )

    username = get_username(verbose)
    fork_name = STUDENT_PROGRESS_FORK_NAME.format(username=username)

    if has_fork(fork_name, verbose):
        info("You already have a fork")
    else:
        warn("You don't have a fork yet, creating one")
        fork(PROGRESS_REPOSITORY_NAME, fork_name, verbose)

    # To avoid sync issues, we save the local progress and delete the local repository
    # before cloning again. This should automatically setup the origin and upstream
    # remotes as well
    local_progress = []
    local_progress_filepath = os.path.join(LOCAL_FOLDER_NAME, "progress.json")
    if os.path.isfile(local_progress_filepath):
        with open(local_progress_filepath, "r") as file:
            local_progress = json.load(file)
    shutil.rmtree(LOCAL_FOLDER_NAME)

    clone_with_custom_name(f"{username}/{fork_name}", LOCAL_FOLDER_NAME, verbose)

    # To reconcile the difference between local and remote progress, we merge by
    # (exercise_name, start_time) which should be unique
    remote_progress = []
    if os.path.isfile(local_progress_filepath):
        with open(local_progress_filepath, "r") as file:
            remote_progress = json.load(file)

    synced_progress = []
    seen = set()
    for entry in local_progress + remote_progress:
        key = (entry["exercise_name"], entry["started_at"])
        if key in seen:
            # Seen this entry before so we can ignore it
            continue
        seen.add(key)
        synced_progress.append(entry)

    synced_progress.sort(
        key=lambda entry: (entry["exercise_name"], entry["started_at"])
    )

    with open(local_progress_filepath, "w") as file:
        file.write(json.dumps(synced_progress))

    # If we have seen more unique entries than what was stored remotely, we need to
    # push the changes
    had_update = len(seen) > len(remote_progress)
    if had_update:
        os.chdir(LOCAL_FOLDER_NAME)
        print("Had update")
        add_all(verbose)
        commit("Sync progress with local machine", verbose)
        push("origin", "main", verbose)

    prs = get_prs(PROGRESS_REPOSITORY_NAME, "main", username, verbose)
    if len(prs) == 0:
        warn("No pull request created for progress. Creating one now")
        pull_request(
            "git-mastery/progress",
            "main",
            f"{username}:main",
            f"[{username}] Progress",
            "Automated",
            verbose,
        )

    success("You have setup the progress tracker for Git-Mastery!")

    gitmastery_config["progress_remote"] = True
    with open(
        gitmastery_root_path / GITMASTERY_CONFIG_NAME, "w"
    ) as gitmastery_config_file:
        gitmastery_config_file.write(json.dumps(gitmastery_config))
