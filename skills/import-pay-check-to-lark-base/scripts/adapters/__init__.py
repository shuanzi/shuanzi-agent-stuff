"""Registry for local statement-format adapters.

Adapters intentionally have a tiny surface: ``detect(path)`` returns a
confidence report and ``parse(path)`` returns a JSON-serialisable batch.
"""

from . import wechat_pay_xlsx


ADAPTERS = {wechat_pay_xlsx.FORMAT_ID: wechat_pay_xlsx}


def get_adapter(format_id):
    """Return a registered adapter or raise a clear error."""
    try:
        return ADAPTERS[format_id]
    except KeyError as exc:
        raise ValueError("unsupported statement format: %s" % format_id) from exc


def iter_adapters():
    """Return adapters in deterministic format-id order."""
    return tuple(ADAPTERS[key] for key in sorted(ADAPTERS))


__all__ = ["ADAPTERS", "get_adapter", "iter_adapters"]
