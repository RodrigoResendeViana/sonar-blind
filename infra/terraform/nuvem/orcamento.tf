# Alerta por e-mail antes de os créditos acabarem. include_credit = false: o orçamento mede o
# uso real, e não o valor depois dos créditos (que ficaria sempre perto de zero).
resource "aws_budgets_budget" "mensal" {
  name         = "sonar-mensal"
  budget_type  = "COST"
  limit_amount = tostring(var.limite_orcamento_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_types {
    include_credit = false
    include_refund = false
  }

  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.email_alertas]
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.email_alertas]
  }
}
