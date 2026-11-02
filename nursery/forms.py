from django import forms
from .age_rules import check_child_age

from accounts.models import User

from .models import Activity, Child, Classroom, Meal


class ChildForm(forms.ModelForm):
    class Meta:
        model = Child
        fields = ["first_name", "last_name", "birth_date", "classroom", "parent", "photo", "allergies", "health_notes"]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "health_notes": forms.Textarea(attrs={"rows": 3}),
            "photo": forms.FileInput(attrs={"accept": "image/*"}),
        }
        labels = {"classroom": "Class", "allergies": "Allergies (comma separated)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = User.objects.filter(role="parent")
        self.fields["parent"].empty_label = "No parent linked"
        self.fields["classroom"].empty_label = "Unassigned"


    def clean_birth_date(self):
        birth_date = self.cleaned_data["birth_date"]
        check_child_age(birth_date)
        return birth_date


class ClassroomForm(forms.ModelForm):
    class Meta:
        model = Classroom
        fields = ["name", "age_group", "capacity", "teacher", "tone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = User.objects.filter(role="teacher")
        self.fields["teacher"].empty_label = "Unassigned"


class MealForm(forms.ModelForm):
    class Meta:
        model = Meal
        fields = ["meal", "food", "amount", "time"]
        widgets = {"time": forms.TimeInput(attrs={"type": "time"})}


class NapForm(forms.Form):
    nap_start = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    nap_end = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    nap_note = forms.CharField(required=False, max_length=200)

    def clean(self):
        d = super().clean()
        if d.get("nap_end") and not d.get("nap_start"):
            raise forms.ValidationError("Add a start time first.")
        if d.get("nap_start") and d.get("nap_end") and d["nap_end"] <= d["nap_start"]:
            raise forms.ValidationError("Nap must end after it starts.")
        return d


class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ["time", "title", "description"]
        widgets = {"time": forms.TimeInput(attrs={"type": "time"})}
