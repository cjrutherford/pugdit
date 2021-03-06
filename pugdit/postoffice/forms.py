from django import forms
from django.db.models import F
from nacl.signing import VerifyKey
from base64 import b64encode, b64decode
import umsgpack
from graphql_relay import from_global_id
from .models import Post, Identity, Vote


class GraphIDShim(forms.TextInput):
    def value_from_datadict(self, data, files, name):
        print('foobar')
        value = super(GraphIDShim, self).value_from_datadict(data, files, name)
        try:
            value = b64decode(value)
        except ValueError as error:
            print('not b64:', value, error)
        else:
            value = value.split(':')[1]
        return value


class PostMarkForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['signature', 'signer']
        widgets = {
            'signer': GraphIDShim()
        }

    def clean(self):
        cleaned_data = super(PostMarkForm, self).clean()
        print('clean postmake', cleaned_data)
        print(self._errors)
        print(self.data)
        signer = cleaned_data['signer']
        raw_signature = b64decode(cleaned_data['signature'].encode('utf8'))
        try:
            raw_message = signer.verify(raw_signature)
            print('raw_message', raw_message)
            message = umsgpack.unpackb(raw_message)
            print('unpacked message:', message)
            self.instance.to, self.instance.link = message
        except ValueError as error:
            raise forms.ValidationError(str(error))
        return cleaned_data

    def save(self):
        obj = super(PostMarkForm, self).save(commit=False)
        obj.pin()
        obj.save()
        return obj


class RegisterIdentityForm(forms.ModelForm):
    public_key = forms.CharField(max_length=77)
    signed_username = forms.CharField()

    class Meta:
        model = Identity
        fields = []
        exclude = ['public_key']

    def __init__(self, data=None, owner=None):
        super(RegisterIdentityForm, self).__init__(data=data)
        self.owner = owner

    def clean_public_key(self):
        data = self.cleaned_data['public_key']
        self.cleaned_data['public_key_base64'] = data
        return b64decode(data.encode('utf8'))

    def clean_signed_username(self):
        data = self.cleaned_data['signed_username']
        return b64decode(data.encode('utf8'))

    def clean(self):
        print('clean', self._errors)
        assert self.owner
        cleaned_data = super(RegisterIdentityForm, self).clean()
        print(cleaned_data, self.owner.username)
        public_key = cleaned_data['public_key']
        signed_username = cleaned_data['signed_username']
        try:
            vk = VerifyKey(public_key)
            username = vk.verify(signed_username)
        except ValueError as error:
            print('validation fail:', error)
            raise forms.ValidationError(str(error))
        except Exception as error:
            print(error)
            print(type(error))
            raise forms.ValidationError(str(error))
        else:
            if username != self.owner.username.encode('utf8'):
                raise forms.ValidationError('Signature was not authorized for this user')
        print('verified', cleaned_data)
        return cleaned_data

    def save(self):
        identity = super(RegisterIdentityForm, self).save(commit=False)
        identity.owner = self.owner
        identity.public_key = self.cleaned_data['public_key_base64']
        identity.save()
        return identity


class VoteForm(forms.ModelForm):
    class Meta:
        model = Vote
        fields = ['post', 'karma']
        widgets = {
            'post': GraphIDShim()
        }

    def clean(self):
        cleaned_data = super(VoteForm, self).clean()
        self.karma_change = cleaned_data['karma'] - self.instance.karma
        return cleaned_data

    def save(self, commit=True):
        obj = super(VoteForm, self).save(commit=commit)
        if self.karma_change:
            Post.objects.filter(id=obj.post_id).update(karma=F('karma')+self.karma_change)
        return obj
