from django.db import models


class TelegramUser(models.Model):
    telegram_id = models.BigIntegerField(unique=True, verbose_name='Telegram ID')
    username = models.CharField(max_length=150, blank=True, verbose_name='Username')
    first_name = models.CharField(max_length=150, blank=True, verbose_name='Имя')
    joined_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата регистрации')

    class Meta:
        verbose_name = 'Telegram пользователь'
        verbose_name_plural = 'Telegram пользователи'

    def __str__(self):
        return f'{self.first_name} (@{self.username}) [{self.telegram_id}]'

    @property
    def display_name(self):
        return self.first_name or self.username or f'User {self.telegram_id}'
