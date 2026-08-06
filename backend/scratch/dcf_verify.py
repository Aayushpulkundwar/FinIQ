import asyncio

async def run():
    from app.db.session import SessionLocal
    from app.services.company import CompanyService
    from app.services.market_data import get_yfinance_dcf_inputs
    from app.services.valuation import compute_dcf_intrinsic_value
    from app.services.valuation_utils import clamp_wacc_with_beta_check, clamp_growth_rate, validate_beta

    db = SessionLocal()
    cs = CompanyService(db)
    companies = await cs.list_companies()
    bharti = next((c for c in companies if c.ticker_symbol == "BHARTIARTL"), None)
    arvind = next((c for c in companies if c.ticker_symbol == "ARVIND"), None)
    db.close()

    for company, label in [(bharti, "BHARTIARTL"), (arvind, "ARVIND")]:
        if not company:
            print(f"{label}: not found in DB")
            continue
        print(f"\n=== {label} ({company.company_name}) ===")
        dcf = await get_yfinance_dcf_inputs(company.ticker_symbol, company.exchange or "")
        if not dcf.get("available"):
            reason = dcf.get("reason", "unknown")
            print(f"  DCF unavailable: {reason}")
            continue

        shares = dcf.get("shares_outstanding")
        fcf = dcf.get("free_cash_flow")
        price = dcf.get("current_price")
        currency = dcf.get("currency")
        cash = dcf.get("cash", 0)
        debt = dcf.get("debt", 0)
        market_cap = dcf.get("market_cap")

        print(f"  Currency: {currency}")
        if shares:
            print(f"  Shares (raw): {shares:,.0f} => {shares/1e6:.1f}M")
        else:
            print("  Shares: None (would show unavailable state)")
        if fcf:
            print(f"  FCF (abs INR): {fcf:,.0f}")
        else:
            print("  FCF: None")
        print(f"  Current Price: {price}")
        if market_cap:
            print(f"  Market Cap (raw): {market_cap:,.0f}")
            print(f"  Market Cap (Cr): {market_cap/1e7:,.0f} Cr")

        if not shares:
            print("  -> RESULT: Shares unavailable -> would raise explicit error, no silent 1B placeholder")
            continue

        if not fcf or fcf <= 0:
            print("  -> RESULT: FCF unavailable/non-positive -> valuation unavailable")
            continue

        beta, beta_src = validate_beta(dcf.get("beta"), None)
        rf = dcf.get("risk_free_rate", 0.04)
        erp = 0.055
        cost_eq = rf + beta * erp
        tax = dcf.get("tax_rate", 0.25)
        cod = dcf.get("cost_of_debt", 0.06) * (1 - tax)
        equity_val = shares * price
        total_cap = equity_val + debt
        eq_w = equity_val / total_cap if total_cap > 0 else 0.8
        dbt_w = debt / total_cap if total_cap > 0 else 0.2
        wacc_raw = eq_w * cost_eq + dbt_w * cod
        wacc, clamped, _ = clamp_wacc_with_beta_check(wacc_raw, beta_src)
        g_rate = dcf.get("fcf_growth_rate", 0.08)
        g_rate, _ = clamp_growth_rate(g_rate, dcf.get("fcf_growth_source", "default"))

        isp, proj_fcfs, tv, ev, eqv = compute_dcf_intrinsic_value(
            baseline_fcf=fcf, fcf_growth_rate=g_rate, wacc=wacc,
            shares_outstanding=shares, perpetuity_growth_rate=0.02,
            cash=cash, debt=debt
        )

        print(f"  WACC: {wacc:.2%} (clamped: {clamped})")
        print(f"  FCF Growth Rate: {g_rate:.2%}")
        print(f"  Enterprise Value (abs INR): {ev:,.0f}")
        print(f"  Enterprise Value (Cr): {ev/1e7:,.0f} Cr")
        print(f"  Equity Value (abs INR): {eqv:,.0f}")
        print(f"  Equity Value (Cr): {eqv/1e7:,.0f} Cr")
        sym = "INR" if currency == "INR" else (currency or "?")
        print(f"  Intrinsic Share Price: {sym} {isp:.2f}")
        if label == "BHARTIARTL":
            real_mcap_cr = 1217786
            real_price = 1952
            print(f"  --- VERIFICATION ---")
            print(f"  Real market cap: ~{real_mcap_cr:,} Cr")
            print(f"  Real current price: {real_price}")
            print(f"  EV magnitude check: {ev/1e7:,.0f} Cr vs real mcap {real_mcap_cr:,} Cr => {'OK within 5x' if abs(ev/1e7 / real_mcap_cr) < 5 else 'STILL WRONG'}")

asyncio.run(run())
