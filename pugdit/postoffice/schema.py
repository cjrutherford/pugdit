from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from graphene_django.forms.mutation import DjangoModelFormMutation, DjangoFormMutation
from graphene.relay import Node
from graphene import ObjectType, Schema, Field, String, Int, List
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login
from django.conf import settings
from django.core.signing import Signer
from base64 import standard_b64decode, standard_b64encode
import requests

from .models import Nexus, Identity, Post, Vote
from .forms import PostMarkForm, RegisterIdentityForm, VoteForm


class NexusNode(DjangoObjectType):
    class Meta:
        model = Nexus
        filter_fields = ['karma', 'is_public']
        interfaces = (Node, )


class IdentityNode(DjangoObjectType):
    email = String()

    class Meta:
        model = Identity
        filter_fields = ['karma', 'is_public', 'owner']
        interfaces = (Node, )

    def resolve_email(self, info, **kwargs):
        if self.owner:
            return self.owner.email
        return None


class AuthUserNode(DjangoObjectType):
    identities = List(IdentityNode)
    storage_key = String()

    class Meta:
        model = User

    def resolve_identities(self, info, **kwargs):
        return self.identity_set.all()

    def resolve_storage_key(self, info, **kwargs):
        signer = Signer()
        #TODO do the right thing
        payload = ''.join([self.username, self.password])
        return signer.sign(payload)


class VoteNode(DjangoObjectType):
    class Meta:
        model = Vote
        interfaces = (Node, )


class PostPayloadNode(ObjectType):
    content_type = String()
    content = String()
    subject = String()
    image = String()
    size = Int()

    class Meta:
        interfaces = (Node, )


class PostNode(DjangoObjectType):
    file = Field(PostPayloadNode)
    user_vote = Field(VoteNode)
    response_count = Int()

    class Meta:
        model = Post
        filter_fields = {
            'karma': ['lte', 'gte'],
            'is_pinned': ['exact'],
            'address': ['startswith', 'exact'],
            'signer': ['exact'],
            'received_timestamp': ['lte', 'gte'],
            'chain_level': ['exact', 'gte']
        }
        interfaces = (Node, )

    def resolve_file(self, info, **kwargs):
        if not self.is_pinned:
            return None
        response = requests.get(settings.IPFS_URL + self.link)
        h = response.headers
        ct = h['Content-Type']
        r = {
            'size': h['Content-Length'],
            'content_type': h['Content-Type']
        }
        if ct == 'message/rfc822' or self.link.endswith('.eml'):
            from email import message_from_string
            msg = message_from_string(response.text)
            c = msg.get_payload()
            r['subject'] = msg.get('Subject')
            r['image'] = msg.get('Image')
            #r['From'] = msg.get('From')
        elif ct.startswith('text'):
            c = response.text
            c = c[:1024*10] #TODO specify max client message length
        else:
            c = None #only transmit text
            #c = standard_b64encode(response.content).decode('utf8')
        r['content'] = c
        #print('resolved file', r)
        return PostPayloadNode(**r)

    def resolve_user_vote(self, info, **kwargs):
        user = info.context.user
        if not user.is_authenticated:
            return None
        vote = Vote.objects.filter(post=self, user=user).first()
        return vote

    def resolve_response_count(self, info, **kwargs):
        return Post.objects.filter(to__startswith=self.address).count()


class Query(ObjectType):
    auth_user = Field(AuthUserNode)
    nexus = Node.Field(NexusNode)
    all_nexus = DjangoFilterConnectionField(NexusNode)

    identity = Node.Field(IdentityNode)
    all_identities = DjangoFilterConnectionField(IdentityNode)

    post = Node.Field(PostNode)
    all_posts = DjangoFilterConnectionField(PostNode, order_by=['to', '-received_timestamp'])

    def resolve_auth_user(self, info, **kwargs):
        user = info.context.user
        print(user)
        if not user.is_authenticated:
            return None
        return user


class PostMarkMutation(DjangoModelFormMutation):
    class Meta:
        form_class = PostMarkForm

    @classmethod
    def get_form_kwargs(cls, root, info, **input):
        kwargs = {"data": input}
        return kwargs

    @classmethod
    def get_form(cls, root, info, **input):
        form_kwargs = cls.get_form_kwargs(root, info, **input)
        form = cls._meta.form_class(**form_kwargs)
        print('postmark get_form:', form)
        print(form.is_valid())
        print(form.errors)
        return form

    @classmethod
    def perform_mutate(cls, form, info):
        onfile = Post.objects.filter(to=form.instance.to, link=form.instance.link, signer=form.cleaned_data['signer']).first()
        if onfile:
            return cls(errors=[], post=onfile)
        obj = form.save()
        print('postmark saved:', obj)
        return cls(errors=[], post=obj)


class RegisterIdentityMutation(DjangoModelFormMutation):
    class Meta:
        form_class = RegisterIdentityForm

    @classmethod
    def get_form_kwargs(cls, root, info, **input):
        kwargs = {"data": input}
        kwargs['owner'] = info.context.user
        return kwargs

    @classmethod
    def get_form(cls, root, info, **input):
        form_kwargs = cls.get_form_kwargs(root, info, **input)
        form = cls._meta.form_class(**form_kwargs)
        print('get_form:', form)
        print(form.is_valid())
        print(form.errors)
        return form

    @classmethod
    def perform_mutate(cls, form, info):
        onfile = Identity.objects.filter(public_key=form.cleaned_data['public_key']).first()
        if onfile:
            return cls(errors=[], identity=onfile)
        obj = form.save()
        print('identity saved:', obj)
        return cls(errors=[], identity=obj)


class AuthenticationMutation(DjangoFormMutation):
    class Meta:
        form_class = AuthenticationForm

    @classmethod
    def get_form_kwargs(cls, root, info, **input):
        kwargs = {"data": input}
        kwargs['request'] = info.context
        return kwargs

    @classmethod
    def perform_mutate(cls, form, info):
        obj = form.get_user()
        if not form.request.COOKIES:
            pass
            #TODO return auth token
        else:
            login(form.request, obj)
        #kwargs = {'authUser': obj}
        return cls(errors=[])#, **kwargs)


class VoteMutation(DjangoModelFormMutation):
    class Meta:
        form_class = VoteForm

    @classmethod
    def get_form_kwargs(cls, root, info, **input):
        user = info.context.user
        post = input['post']
        instance = Vote.objects.filter(post=post, user=user).first()
        kwargs = {
            "data": input,
            "instance": instance,
        }
        return kwargs

    @classmethod
    def perform_mutate(cls, form, info):
        user = info.context.user
        obj = form.save(commit=False)
        obj.user = user
        obj.save()
        return cls(errors=[], vote=obj)


class Mutation(ObjectType):
    authentication = AuthenticationMutation.Field()
    post_mark = PostMarkMutation.Field()
    register_identity = RegisterIdentityMutation.Field()
    vote = VoteMutation.Field()


schema = Schema(query=Query, mutation=Mutation)
