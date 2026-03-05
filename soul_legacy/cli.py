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


@main.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--section", "-s", type=click.Choice(list(SECTION_FIELDS.keys())),
              help="Override auto-detected section")
@click.option("--record-id", "-r", help="Link to existing record ID")
@click.option("--azure", is_flag=True, help="Use Azure OCR + embeddings")
def ingest(file_path, section, record_id, azure):
    """Ingest a document into the vault (PDF, image, Word)"""
    from .ingest import ingest_file
    v = get_vault()

    config = {}
    if azure:
        import json as _json, os as _os
        try:
            keys = _json.load(open(_os.path.expanduser("~/.openclaw/api_keys.json")))
            az   = keys.get("azure_openai", {})
            config = {
                "ocr_mode":       "azure",
                "embed_mode":     "azure",
                "azure_endpoint": az.get("endpoint"),
                "azure_key":      az.get("api_key"),
            }
        except:
            console.print("[yellow]Could not load Azure keys — falling back to local[/yellow]")

    try:
        result = ingest_file(v, file_path, section=section,
                             record_id=record_id, config=config)
        console.print(Panel(
            f"[bold]Section:[/bold]  {result['section']}/{result['record_id']}\n"
            f"[bold]File:[/bold]     {result['filename']}\n"
            f"[bold]Chunks:[/bold]   {result['chunks']}\n"
            f"[bold]Method:[/bold]   {result['method']}\n"
            f"[bold]Dims:[/bold]     {result['dims']}",
            title="[green]✅ Ingested[/green]", border_style="green"
        ))
    except Exception as e:
        console.print(f"[red]❌ {e}[/red]")


@main.command()
@click.argument("query")
@click.option("--section", "-s", type=click.Choice(list(SECTION_FIELDS.keys())))
@click.option("--top-k", default=5)
@click.option("--azure", is_flag=True)
def search(query, section, top_k, azure):
    """Semantic search across all ingested documents"""
    from .ingest import search as do_search
    v      = get_vault()
    config = _azure_config() if azure else {}

    results = do_search(v, query, top_k=top_k, section=section, config=config)
    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    for i, r in enumerate(results, 1):
        console.print(Panel(
            f"[dim]{r['text'][:400]}...[/dim]",
            title=f"[cyan]#{i} {r['doc_id']} (score: {r['score']})[/cyan]",
            border_style="dim"
        ))


def _azure_config():
    import json as _json, os as _os
    try:
        keys = _json.load(open(_os.path.expanduser("~/.openclaw/api_keys.json")))
        az   = keys.get("azure_openai", {})
        return {
            "ocr_mode":       "azure",
            "embed_mode":     "azure",
            "azure_endpoint": az.get("endpoint"),
            "azure_key":      az.get("api_key"),
        }
    except:
        return {}


@main.command("soul-chat")
@click.option("--api-key", envvar="ANTHROPIC_API_KEY")
@click.option("--model", default="claude-haiku-4-5")
@click.option("--mode", type=click.Choice(["auto","rag","rlm"]), default="auto",
              help="auto=router decides, rag=fast lookup, rlm=exhaustive synthesis")
@click.option("--azure", is_flag=True, help="Use Azure embeddings for RAG")
def soul_chat(api_key, model, mode, azure):
    """Full soul.py v2.0 chat — RAG + RLM + Darwin + Memory"""
    from .soul_integration import SoulLegacyAgent
    v = get_vault()

    try:
        agent = SoulLegacyAgent(v, api_key=api_key, model=model)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    console.print(Panel.fit(
        "[bold cyan]🏛️  Estate Advisor — soul.py v2.0[/bold cyan]\n"
        "[dim]RAG + RLM + Darwin · Type 'exit' to quit · '/route' to see last route[/dim]",
        border_style="cyan"
    ))
    console.print(f"[dim]Mode: {mode} | Model: {model}[/dim]\n")

    last_result = None
    while True:
        console.print()
        q = Prompt.ask("[cyan]You[/cyan]")
        if q.lower() in ("exit", "quit", "q"):
            break
        if q == "/route" and last_result:
            console.print(f"[dim]Route: {last_result.get('route')} | "
                          f"{last_result.get('total_ms')}ms[/dim]")
            continue
        if q == "/soul":
            console.print(Panel(agent.soul(), title="[cyan]Current Advisor Persona[/cyan]",
                                border_style="dim"))
            continue
        if q == "/memory":
            mem = (v.vault.dir if hasattr(v,'vault') else v.dir)
            import os as _os
            mp = _os.path.join(v.dir, "MEMORY.md")
            if _os.path.exists(mp):
                console.print(open(mp).read()[-2000:])
            continue

        with console.status(f"[dim]Thinking ({mode})...[/dim]"):
            last_result = agent.ask(q)

        route_tag = f"[dim][{last_result.get('route','?')} · {last_result.get('total_ms')}ms][/dim]"
        console.print(f"\n[bold]Advisor:[/bold] {last_result['answer']}")
        console.print(route_tag)


@main.command()
def memory():
    """Show vault interaction memory (MEMORY.md)"""
    v  = get_vault()
    mp = os.path.join(v.dir, "MEMORY.md")
    if not os.path.exists(mp):
        console.print("[dim]No memory yet. Start chatting![/dim]")
        return
    text = open(mp).read()
    console.print(Panel(text[-3000:], title="[cyan]Vault Memory[/cyan]", border_style="dim"))


@main.command()
@click.option("--host", default="127.0.0.1", help="Host (use 0.0.0.0 for Railway/Docker)")
@click.option("--port", default=8080, help="Port")
@click.option("--cloud", is_flag=True, help="Cloud mode — enable multi-tenant accounts")
@click.option("--reload", is_flag=True, help="Auto-reload on code changes (dev)")
def serve(host, port, cloud, reload):
    """Start the soul-legacy web UI"""
    import uvicorn
    if cloud:
        os.environ["SOUL_LEGACY_MODE"] = "cloud"
        console.print(f"[cyan]🌐 Cloud mode — multi-tenant accounts enabled[/cyan]")
    else:
        console.print(f"[cyan]🏠 Local mode — single vault, passphrase auth[/cyan]")
    console.print(f"[bold]Open:[/bold] http://{host}:{port}\n")
    uvicorn.run("soul_legacy.server.app:app",
                host=host, port=port, reload=reload)
