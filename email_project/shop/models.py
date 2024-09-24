from django.db import models

class Order(models.Model):
    order_id = models.CharField(max_length=50)
    product_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    order_date = models.DateField()
    customer_email = models.EmailField()
    total_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f'Заказ {self.order_id}'


class ParsingConfig(models.Model):
    email = models.EmailField()
    column_mappings = models.JSONField(help_text='Соответствие колонок Excel и полей модели Order')
    schedule = models.CharField(max_length=50, help_text='CRON выражение для Airflow')

    def __str__(self):
        return self.email