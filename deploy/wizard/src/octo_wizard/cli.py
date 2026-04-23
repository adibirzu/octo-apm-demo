"""Interactive TUI.

The wizard runs five phases:

    1. Detect OCI profile + confirm region
    2. Pick compartment (or create)
    3. Pick runtime (OKE existing/new, VM existing/new)
    4. Pick DB (ATP existing/new, Postgres dev)
    5. Review plan + execute (dry-run by default)

Every side effect goes through subprocess.run; no SDK mutations happen
in the wizard itself.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from typing import Any

try:
    import questionary  # type: ignore
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "wizard requires rich + questionary — pip install '.[dev]' or install extras"
    ) from exc

from .discovery import Discovery, TenancyInventory
from .plan import DBChoice, DeploymentPlan, PlanAction, RuntimeChoice

console = Console()


def _banner() -> None:
    console.print(Panel.fit(
        "[bold cyan]octo-apm-demo — provisioning wizard[/bold cyan]\n"
        "discovers your tenancy, plans the deploy, then dispatches.",
        border_style="cyan",
    ))


def _print_inventory(inv: TenancyInventory) -> None:
    t = Table(title="Tenancy inventory", show_lines=False)
    t.add_column("Field", style="cyan")
    t.add_column("Value")
    for k, v in inv.summary().items():
        t.add_row(k, str(v))
    console.print(t)


def _print_plan(plan: DeploymentPlan) -> None:
    t = Table(title="Proposed deployment plan", show_lines=True)
    t.add_column("#", style="dim", width=3)
    t.add_column("Kind", style="green")
    t.add_column("Command", style="cyan", no_wrap=False)
    t.add_column("Description")
    for i, a in enumerate(plan.actions, 1):
        t.add_row(str(i), a.kind, a.command, a.description)
    console.print(t)


def _execute(plan: DeploymentPlan, *, dry_run: bool) -> int:
    failures = 0
    for i, action in enumerate(plan.actions, 1):
        console.print(f"[bold]Step {i}[/bold] — {action.description}")
        console.print(f"  [cyan]$ {action.command}[/cyan]")

        if dry_run:
            console.print("  [yellow](dry-run — not executed)[/yellow]")
            continue

        if action.requires_confirmation:
            ok = questionary.confirm(
                f"Run step {i} ({action.description})?", default=True
            ).ask()
            if not ok:
                console.print("  [yellow]skipped[/yellow]")
                continue

        env = os.environ.copy()
        env.update(action.env)
        cmd_parts = shlex.split(action.command)
        result = subprocess.run(cmd_parts, env=env)
        if result.returncode != 0:
            failures += 1
            console.print(f"  [red]failed (exit {result.returncode})[/red]")
            if not questionary.confirm("Continue?", default=False).ask():
                return failures

    return failures


def main() -> int:
    _banner()

    profile = questionary.text(
        "OCI config profile (~/.oci/config):", default="DEFAULT"
    ).ask()
    if not profile:
        return 2

    console.print("Discovering tenancy…")
    try:
        disc = Discovery(profile=profile)
        # Phase 1: tenancy + regions
        tid, tname = disc.tenancy()
        regions = disc.regions()
    except Exception as exc:
        console.print(f"[red]OCI discovery failed: {exc}[/red]")
        return 2

    region = questionary.select("Region:", choices=regions).ask()
    if not region:
        return 2

    disc_r = Discovery(profile=profile, region=region)

    # Phase 2: compartment
    compartments = disc_r.compartments()
    comp_choice = questionary.select(
        "Compartment:",
        choices=[f"{c.name} [{c.id[-10:]}]" for c in compartments],
    ).ask()
    if not comp_choice:
        return 2
    comp = next(c for c in compartments if c.id.endswith(comp_choice.split("[")[1][:-1]))

    console.print(f"Loading inventory for compartment [cyan]{comp.name}[/cyan]…")
    inv = disc_r.build_inventory(compartment_id=comp.id)
    _print_inventory(inv)

    # Phase 3: runtime
    runtime_str = questionary.select(
        "Runtime:",
        choices=[c.value for c in RuntimeChoice],
    ).ask()
    runtime = RuntimeChoice(runtime_str)

    existing_cluster_id = ""
    if runtime == RuntimeChoice.OKE_EXISTING:
        if not inv.oke_clusters:
            console.print("[red]No OKE clusters in this compartment — aborting.[/red]")
            return 2
        pick = questionary.select(
            "OKE cluster:",
            choices=[f"{c.name} [{c.id[-10:]}]" for c in inv.oke_clusters],
        ).ask()
        existing_cluster_id = next(
            c.id for c in inv.oke_clusters if c.id.endswith(pick.split("[")[1][:-1])
        )

    # Phase 4: DB
    db_str = questionary.select(
        "Database:",
        choices=[c.value for c in DBChoice],
    ).ask()
    db = DBChoice(db_str)

    existing_atp_id = ""
    if db == DBChoice.ATP_EXISTING:
        if not inv.atps:
            console.print("[red]No ATPs in this compartment — aborting.[/red]")
            return 2
        pick = questionary.select(
            "ATP:",
            choices=[f"{a.name} [{a.id[-10:]}]" for a in inv.atps],
        ).ask()
        existing_atp_id = next(a.id for a in inv.atps if a.id.endswith(pick.split("[")[1][:-1]))

    dns_domain = questionary.text(
        "DNS domain (e.g. cyber-sec.ro):", default="cyber-sec.ro"
    ).ask()

    # Build plan
    plan = DeploymentPlan(
        runtime=runtime,
        db=db,
        compartment_id=comp.id,
        compartment_name=comp.name,
        region=region,
        dns_domain=dns_domain,
        ocir_namespace=inv.ocir_namespace,
        existing_cluster_id=existing_cluster_id,
        existing_atp_id=existing_atp_id,
    )
    plan.compose()
    _print_plan(plan)

    mode = questionary.select(
        "Mode:",
        choices=["dry-run (print only)", "apply (execute with confirmations)"],
    ).ask()

    failures = _execute(plan, dry_run=mode.startswith("dry-run"))
    if failures:
        console.print(f"[red]{failures} step(s) failed.[/red]")
        return 1
    console.print("[green]done.[/green]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
