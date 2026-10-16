from django import forms

from apps.mlapp.models import MLModel, MLModelStatus
from trading.strategies.registry import available_strategies


class BacktestCreateForm(forms.Form):
    name = forms.CharField(max_length=120, required=False, label="Experiment name")
    symbol = forms.CharField(max_length=32, initial="BTCUSDT")
    strategy_id = forms.ChoiceField(label="Strategy")
    ml_model_id = forms.ChoiceField(
        required=False,
        label="ML model (for ml_classifier)",
        help_text="Required when strategy is ml_classifier",
    )
    timeframe = forms.ChoiceField(
        choices=[
            ("1h", "1h"),
            ("4h", "4h"),
            ("1d", "1d"),
        ],
        initial="4h",
    )
    open_rsi = forms.FloatField(initial=5.0, min_value=0, max_value=25, label="RSI offset")
    ml_threshold = forms.FloatField(
        initial=0.58,
        min_value=0.5,
        max_value=0.95,
        label="ML probability threshold",
        required=False,
    )
    fee_rate = forms.FloatField(initial=0.00045, min_value=0, label="Fee rate (per side)")
    slippage_rate = forms.FloatField(initial=0.0, min_value=0, label="Slippage rate")
    tp_sl_ratio = forms.FloatField(initial=1.5, min_value=0.1, label="TP / SL ratio")
    sl_limit = forms.FloatField(initial=0.10, min_value=0.01, max_value=0.5, label="SL limit")
    notional = forms.FloatField(initial=100.0, min_value=1, label="Position notional (USDT)")
    enable_trailing = forms.BooleanField(required=False, initial=True, label="Enable trailing")
    data_start = forms.DateTimeField(
        required=False,
        label="Data start (UTC)",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    data_end = forms.DateTimeField(
        required=False,
        label="Data end (UTC)",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["strategy_id"].choices = [
            (sid, sid) for sid in available_strategies()
        ]
        ml_qs = MLModel.objects.filter(status=MLModelStatus.READY)
        if user is not None:
            ml_qs = ml_qs.filter(models_q_owner(user))
        self.fields["ml_model_id"].choices = [("", "—")] + [
            (str(m.pk), f"#{m.pk} {m.name} ({m.symbol.symbol})")
            for m in ml_qs.select_related("symbol")[:50]
        ]
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("strategy_id") == "ml_classifier" and not cleaned.get("ml_model_id"):
            self.add_error("ml_model_id", "Select a ready ML model for ml_classifier.")
        return cleaned


def models_q_owner(user):
    from django.db.models import Q

    return Q(owner=user) | Q(owner__isnull=True)


class StrategyLabForm(forms.Form):
    name_prefix = forms.CharField(max_length=40, initial="lab")
    symbol = forms.CharField(max_length=32, initial="BTCUSDT")
    strategy_id = forms.ChoiceField(initial="rsi_macd_stoch")
    timeframe = forms.ChoiceField(
        choices=[("1h", "1h"), ("4h", "4h"), ("1d", "1d")],
        initial="4h",
    )
    open_rsi_values = forms.CharField(
        initial="3,5,7",
        label="open_rsi values",
        help_text="Comma-separated",
    )
    tp_sl_ratio_values = forms.CharField(
        initial="1.2,1.5,2.0",
        label="tp_sl_ratio values",
        help_text="Comma-separated",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["strategy_id"].choices = [
            (sid, sid) for sid in available_strategies() if sid != "ml_classifier"
        ]
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def _parse_floats(self, raw: str) -> list[float]:
        vals = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            vals.append(float(part))
        if not vals:
            raise forms.ValidationError("Provide at least one numeric value.")
        return vals

    def clean_open_rsi_values(self):
        return self._parse_floats(self.cleaned_data["open_rsi_values"])

    def clean_tp_sl_ratio_values(self):
        return self._parse_floats(self.cleaned_data["tp_sl_ratio_values"])


class RunFilterForm(forms.Form):
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses")]
        + [
            ("queued", "Queued"),
            ("running", "Running"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
    )
    strategy_id = forms.CharField(required=False, label="Strategy")
    symbol = forms.CharField(required=False, label="Symbol")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class CompareForm(forms.Form):
    run_ids = forms.CharField(
        label="Run IDs",
        help_text="Comma-separated run ids, e.g. 1,2,3",
        widget=forms.TextInput(attrs={"placeholder": "1, 2"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["run_ids"].widget.attrs.setdefault("class", "form-control")

    def clean_run_ids(self) -> list[int]:
        raw = self.cleaned_data["run_ids"]
        parts = [p.strip() for p in raw.replace(" ", ",").split(",") if p.strip()]
        if len(parts) < 2:
            raise forms.ValidationError("Provide at least two run ids.")
        ids: list[int] = []
        for part in parts:
            if not part.isdigit():
                raise forms.ValidationError(f"Invalid run id: {part}")
            ids.append(int(part))
        return ids
