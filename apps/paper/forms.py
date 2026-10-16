from django import forms

from apps.paper.models import PaperMode, PaperSession
from trading.strategies.registry import available_strategies


class PaperSessionForm(forms.ModelForm):
    symbols_text = forms.CharField(
        label="Symbols",
        help_text="Comma-separated, e.g. BTCUSDT,ETHUSDT",
        initial="BTCUSDT",
    )
    open_rsi = forms.FloatField(initial=5.0, min_value=0, max_value=25)
    fee_rate = forms.FloatField(initial=0.00045, min_value=0)
    tp_sl_ratio = forms.FloatField(initial=1.5, min_value=0.1)
    sl_limit = forms.FloatField(initial=0.10, min_value=0.01, max_value=0.5)
    enable_trailing = forms.BooleanField(required=False, initial=True)

    class Meta:
        model = PaperSession
        fields = (
            "name",
            "mode",
            "strategy_id",
            "timeframe",
            "notional",
            "leverage",
            "is_active",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["strategy_id"] = forms.ChoiceField(
            choices=[(s, s) for s in available_strategies()]
        )
        self.fields["mode"].choices = PaperMode.choices
        self.fields["timeframe"] = forms.ChoiceField(
            choices=[("1h", "1h"), ("4h", "4h"), ("1d", "1d")]
        )
        if self.instance and self.instance.pk:
            self.fields["symbols_text"].initial = ",".join(self.instance.symbols or [])
            params = self.instance.strategy_params or {}
            exec_cfg = self.instance.execution_config or {}
            self.fields["open_rsi"].initial = params.get("open_rsi", 5.0)
            self.fields["fee_rate"].initial = exec_cfg.get("fee_rate", 0.00045)
            self.fields["tp_sl_ratio"].initial = exec_cfg.get("tp_sl_ratio", 1.5)
            self.fields["sl_limit"].initial = exec_cfg.get("sl_limit", 0.10)
            self.fields["enable_trailing"].initial = exec_cfg.get("enable_trailing", True)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean_symbols_text(self) -> list[str]:
        raw = self.cleaned_data["symbols_text"]
        symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
        if not symbols:
            raise forms.ValidationError("Provide at least one symbol.")
        return symbols

    def save(self, commit=True):
        instance: PaperSession = super().save(commit=False)
        instance.symbols = self.cleaned_data["symbols_text"]
        instance.strategy_params = {
            "open_rsi": self.cleaned_data["open_rsi"],
            "warm_up": 60,
        }
        instance.execution_config = {
            "fee_rate": self.cleaned_data["fee_rate"],
            "tp_sl_ratio": self.cleaned_data["tp_sl_ratio"],
            "sl_limit": self.cleaned_data["sl_limit"],
            "enable_trailing": bool(self.cleaned_data.get("enable_trailing")),
        }
        if commit:
            instance.save()
        return instance
