"""Entry point: python -m voice"""
from voice.config import load_config
from voice.pipeline import Pipeline


def main() -> None:
    cfg = load_config()
    Pipeline(cfg).run()


if __name__ == "__main__":
    main()
