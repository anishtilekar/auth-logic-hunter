from pathlib import Path

import typer

from app.pipeline.stage1_state_model.builder import build_application_model

app = typer.Typer()


@app.command()
def version() -> None:
    """Print the CLI version."""
    typer.echo("auth-logic-hunter 0.1.0")


@app.command(name="build-model")
def build_model(
    target: Path = typer.Option(..., help="Target app root (e.g. targets/crapi)"),
    out: Path = typer.Option(Path("application-model.json"), help="Output JSON path"),
) -> None:
    """Run Stage 1: build the Application Model from a target's OpenAPI spec + source."""
    model = build_application_model(target)
    out.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(
        f"Wrote {out} — {len(model.resources)} resources, "
        f"{len(model.endpoints)} endpoints, {len(model.transitions)} transitions"
    )


if __name__ == "__main__":
    app()
