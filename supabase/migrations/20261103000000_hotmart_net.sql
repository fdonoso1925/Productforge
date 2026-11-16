-- Hotmart: facturación neta REAL. Sale del endpoint de comisiones (lo que Hotmart le paga al
-- usuario por cada venta, ya con tarifa, impuestos retenidos y reparto con coproductores o
-- afiliados), no de una estimación. Nulo = todavía no se leyó la comisión de esa venta.

alter table hotmart_sales
  add column net_usd     numeric(14, 2),   -- comisión del usuario en USD (su parte de la venta)
  add column payout_rate numeric(14, 8);   -- USD por 1 unidad de `currency` que aplicó Hotmart
