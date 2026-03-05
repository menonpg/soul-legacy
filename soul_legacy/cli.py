"""
soul-legacy CLI
soul-legacy init        — create a new vault
soul-legacy add         — add a record to a section
soul-legacy list        — list records in a section
soul-legacy show        — show a record
soul-legacy chat        — ask questions about your estate
soul-legacy summary     — generate full estate summary
soul-legacy export      — export decrypted vault (for attorney)
soul-legacy status      — vault health check
"""
import click, json, os, sys
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import print as rprint

console = Console()

DEFAULT_VAULT = os.path.expanduser("~/.soul-legacy/vault")
DEFAULT_CFG   = os.path.expanduser("~/.soul-legacy/config.json")

SECTION_FIELDS = {
    "assets": ["name", "type", "institution", "value_usd", "beneficiary", "notes"],
    "insurance": ["type", "provider", "policy_number", "coverage_usd", "beneficiary", "notes"],
    "legal": ["type", "date_signed", "attorney", "location", "notes"],
    "debts": ["type", "creditor", "balance_usd", "monthly_payment", "interest_rate", "notes"],
    "contacts": ["role", "name", "firm", "phone", "email", "notes"],
    "beneficiaries": ["name", "relationship", "contact", "share_pct", "notes"],
    "digital": ["type", "platform", "username", "instructions", "notes"],
    "wishes": ["category", "description", "recipient", "notes"],
}

SECTION_TYPES = {
    "assets": ["bank_account", "brokerage", "real_estate", "vehicle", "crypto", "business", "other"],
    "insurance": ["life", "health", "property", "auto", "umbrella", "other"],
    "legal": ["will", "trust", "power_of_attorney", "healthcare_directive", "other"],
    "debts": ["mortgage", "auto_loan", "student_loan", "credit_card", "other"],
    "contacts": ["attorney", "accountant", "executor", "trustee", "doctor", "financial_advisor", "other"],
    "wishes": ["funeral", "medical", "personal_property", "message", "other"],
}


def get_vault(passphrase=None):
    from .vault import Vault
    cfg = {}
    if os.path.exists(DEFAULT_CFG):
        cfg = json.load(open(DEFAULT_CFG))
    vault_dir = cfg.get("vault_dir", DEFAULT_VAULT)
    if not passphrase:
        passphrase = click.prompt("🔑 Vault passphrase", hide_input=True)
    v = Vault(vault_dir, passphrase)
    if not v.verify_passphrase():
        console.print("[red]❌ Wrong passphrase[/red]")
        sys.exit(1)
    return v


def save_config(vault_dir):
    os.makedirs(os.path.dirname(DEFAULT_CFG), exist_ok=True)
    json.dump({"vault_dir": vault_dir}, open(DEFAULT_CFG, "w"))


@click.group()
def main():
    """🏛️  soul-legacy — your digital estate vault"""
    pass


@main.command()
def init():
    """Create a new vault with guided onboarding"""
    console.print(Panel.fit(
        "[bold cyan]🏛️  soul-legacy[/bold cyan]\n"
        "[dim]Your digital estate vault — local-first, encrypted, LLM-queryable[/dim]",
        border_style="cyan"
    ))
    console.print()

    # Vault location
    vault_dir = Prompt.ask(
        "📁 Where should your vault live",
        default=DEFAULT_VAULT
    )
    vault_dir = os.path.expanduser(vault_dir)

    if os.path.exists(os.path.join(vault_dir, ".salt")):
        console.print(f"[yellow]⚠️  A vault already exists at {vault_dir}[/yellow]")
        if not Confirm.ask("Overwrite?", default=False):
            sys.exit(0)

    # Owner info
    console.print()
    owner_name  = Prompt.ask("👤 Your full legal name")
    owner_email = Prompt.ask("📧 Your email (optional)", default="")

    # Passphrase
    console.print()
    console.print("[dim]Choose a strong passphrase. This encrypts everything.[/dim]")
    console.print("[dim]Store it somewhere safe — if lost, vault is unrecoverable.[/dim]")
    console.print()
    while True:
        pp1 = click.prompt("🔑 Choose passphrase", hide_input=True)
        pp2 = click.prompt("🔑 Confirm passphrase", hide_input=True)
        if pp1 == pp2:
            passphrase = pp1
            break
        console.print("[red]Passphrases don't match. Try again.[/red]")

    # Create vault
    from .vault import Vault
    v = Vault(vault_dir, passphrase)
    v.init(owner_name, owner_email)
    save_config(vault_dir)

    console.print()
    console.print(f"[green]✅ Vault created at {vault_dir}[/green]")
    console.print()

    # Offer to add first records
    console.print("[bold]Let's add your first records.[/bold]")
    console.print("[dim]Press Enter to skip any section.[/dim]")
    console.print()

    sections_order = ["legal", "assets", "insurance", "contacts", "beneficiaries"]
    for section in sections_order:
        if Confirm.ask(f"  Add a [cyan]{section}[/cyan] record now?", default=False):
            _add_interactive(v, section)

    console.print()
    console.print(Panel.fit(
        f"[bold green]🏛️  Vault ready[/bold green]\n\n"
        f"  [dim]soul-legacy add <section>   — add records[/dim]\n"
        f"  [dim]soul-legacy list <section>  — list records[/dim]\n"
        f"  [dim]soul-legacy chat            — ask questions[/dim]\n"
        f"  [dim]soul-legacy summary         — full estate overview[/dim]",
        border_style="green"
    ))


def _add_interactive(vault, section):
    from .vault import SECTIONS
    fields  = SECTION_FIELDS.get(section, [])
    types   = SECTION_TYPES.get(section, [])
    record  = {}
    console.print(f"\n[bold cyan]Adding {section} record[/bold cyan]")

    if types:
        console.print(f"  Types: {', '.join(types)}")

    for field in fields:
        val = Prompt.ask(f"  {field}", default="")
        if val:
            record[field] = val

    if not record:
        return

    import uuid
    record["id"] = str(uuid.uuid4())[:8]
    vault.write(section, record["id"], record)
    console.print(f"  [green]✅ Saved {section}/{record['id']}[/green]")
    return record


@main.command()
@click.argument("section", type=click.Choice(list(SECTION_FIELDS.keys())))
def add(section):
    """Add a record to a vault section"""
    v = get_vault()
    _add_interactive(v, section)


@main.command()
@click.argument("section", type=click.Choice(list(SECTION_FIELDS.keys())))
def list(section):
    """List all records in a section"""
    v    = get_vault()
    ids  = v.list(section)
    if not ids:
        console.print(f"[dim]No {section} records yet.[/dim]")
        return

    table = Table(title=f"📋 {section.upper()}", border_style="dim")
    table.add_column("ID",   style="cyan",  width=10)
    table.add_column("Name/Type", style="white")
    table.add_column("Notes",     style="dim")

    for rid in ids:
        r = v.read(section, rid)
        name  = r.get("name") or r.get("type") or r.get("platform") or r.get("category") or rid
        notes = (r.get("notes") or "")[:60]
        table.add_row(rid, name, notes)

    console.print(table)


@main.command()
@click.argument("section", type=click.Choice(list(SECTION_FIELDS.keys())))
@click.argument("record_id")
def show(section, record_id):
    """Show a specific record"""
    v = get_vault()
    r = v.read(section, record_id)
    console.print(Panel(
        json.dumps(r, indent=2, default=str),
        title=f"[cyan]{section}/{record_id}[/cyan]",
        border_style="cyan"
    ))


@main.command()
@click.argument("section", type=click.Choice(list(SECTION_FIELDS.keys())))
@click.argument("record_id")
def delete(section, record_id):
    """Delete a record"""
    v = get_vault()
    if Confirm.ask(f"Delete {section}/{record_id}?", default=False):
        v.delete(section, record_id)
        console.print(f"[green]Deleted {section}/{record_id}[/green]")


@main.command()
@click.option("--api-key", envvar="ANTHROPIC_API_KEY")
@click.option("--model", default="claude-haiku-4-5")
def chat(api_key, model):
    """Chat with your estate data in plain English"""
    v = get_vault()
    console.print(Panel.fit(
        "[bold cyan]🏛️  Estate Advisor[/bold cyan]\n"
        "[dim]Ask anything about your estate. Type 'exit' to quit.[/dim]",
        border_style="cyan"
    ))

    from .chat import chat as do_chat
    while True:
        console.print()
        q = Prompt.ask("[cyan]You[/cyan]")
        if q.lower() in ("exit", "quit", "q"):
            break
        with console.status("Thinking..."):
            answer = do_chat(v, q, api_key=api_key, model=model)
        console.print(f"\n[bold]Advisor:[/bold] {answer}")


@main.command()
def summary():
    """Generate a plain-English estate summary"""
    v       = get_vault()
    records = v.all_records()
    meta    = v.meta()

    console.print(Panel.fit(
        f"[bold]🏛️  Estate Summary — {meta['owner_name']}[/bold]\n"
        f"[dim]Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]",
        border_style="cyan"
    ))

    total_assets = sum(
        float(r.get("value_usd") or 0) for r in records.get("assets", [])
    )
    total_debts  = sum(
        float(r.get("balance_usd") or 0) for r in records.get("debts", [])
    )
    net_worth    = total_assets - total_debts

    table = Table(border_style="dim", show_header=False)
    table.add_column("Section", style="cyan")
    table.add_column("Count",   style="white")
    table.add_column("Detail",  style="dim")

    for section, items in records.items():
        if not items:
            continue
        detail = ""
        if section == "assets":
            detail = f"Total value: ${total_assets:,.0f}"
        elif section == "debts":
            detail = f"Total owed: ${total_debts:,.0f}"
        table.add_row(section.upper(), str(len(items)), detail)

    console.print(table)
    console.print()
    if total_assets or total_debts:
        color = "green" if net_worth >= 0 else "red"
        console.print(f"  [bold]Estimated net worth: [{color}]${net_worth:,.0f}[/{color}][/bold]")

    missing = [s for s in ["legal", "beneficiaries", "contacts"]
               if not records.get(s)]
    if missing:
        console.print()
        console.print(f"  [yellow]⚠️  Missing sections: {', '.join(missing)}[/yellow]")
        console.print(f"  [dim]Run: soul-legacy add <section>[/dim]")


@main.command()
def status():
    """Vault health check"""
    v    = get_vault()
    meta = v.meta()
    fp   = v.fingerprint()

    console.print(Panel(
        f"[bold]Owner:[/bold]   {meta['owner_name']}\n"
        f"[bold]Created:[/bold] {meta['created_at'][:10]}\n"
        f"[bold]Updated:[/bold] {meta['updated_at'][:10]}\n"
        f"[bold]Storage:[/bold] {meta['storage']}\n"
        f"[bold]Hash:[/bold]    [dim]{fp[:32]}...[/dim]\n"
        f"[bold]Anchored:[/bold] {'✅ Yes' if meta.get('blockchain_anchored') else '❌ Not yet'}",
        title="[cyan]🏛️  Vault Status[/cyan]",
        border_style="cyan"
    ))
