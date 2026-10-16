from django import forms


class MLTrainForm(forms.Form):
    name = forms.CharField(max_length=120, required=False)
    symbol = forms.CharField(max_length=32, initial="BTCUSDT")
    timeframe = forms.ChoiceField(
        choices=[("1h", "1h"), ("4h", "4h"), ("1d", "1d")],
        initial="4h",
    )
    train_ratio = forms.FloatField(initial=0.7, min_value=0.5, max_value=0.9)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
