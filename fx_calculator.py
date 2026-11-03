"""Calculate FX returns and the SEK cost of a euro payment.

All exchange rates below are artificial teaching values.
EUR/SEK means the number of SEK required to buy one EUR.
"""


def simple_return(old_rate, new_rate):
    """Calculate a decimal return: 0.01 means 1%."""
    return (new_rate - old_rate) / old_rate


def payment_cost_sek(amount_eur, sek_per_eur):
    """Calculate how many SEK are needed to pay an amount in EUR."""
    return amount_eur * sek_per_eur


def main():
    # DAY 1: your original sequence, now using the two functions above.
    eur_sek = [11.00, 11.22, 11.11, 11.33, 11.20]
    eur_payment = 100_000

    print("Day 1 example: consecutive exchange-rate changes")

    for day in range(1, len(eur_sek)):
        previous = eur_sek[day - 1]
        current = eur_sek[day]

        fx_return = simple_return(previous, current)
        old_cost = payment_cost_sek(eur_payment, previous)
        new_cost = payment_cost_sek(eur_payment, current)
        cost_change = new_cost - old_cost

        print(
            f"Move {day}: "
            f"FX return = {fx_return:.2%}, "
            f"change in payment cost = {cost_change:+,.0f} SEK"
        )

    # DAY 2: inspect one payment in detail.
    # Practice A: change new_rate to 10.89, then run this file again.
    # Practice B: keep those rates and change amount_eur to 250_000.
    old_rate = 11.00
    new_rate = 11.11
    amount_eur = 100_000

    fx_return = simple_return(old_rate, new_rate)
    old_cost = payment_cost_sek(amount_eur, old_rate)
    new_cost = payment_cost_sek(amount_eur, new_rate)
    cost_change = new_cost - old_cost

    print("\nDay 2 example: a company that owes euros")
    print(f"Euro payment: {amount_eur:,.0f} EUR")
    print(f"Old rate: {old_rate:.2f} SEK per EUR")
    print(f"New rate: {new_rate:.2f} SEK per EUR")
    print(f"FX return: {fx_return:.2%}")
    print(f"Old payment cost: {old_cost:,.0f} SEK")
    print(f"New payment cost: {new_cost:,.0f} SEK")
    print(f"Change in payment cost: {cost_change:+,.0f} SEK")

    if cost_change > 0:
        print("The company needs more SEK to pay the same euro amount.")
    elif cost_change < 0:
        print("The company needs fewer SEK to pay the same euro amount.")
    else:
        print("The payment cost has not changed.")


# Run the examples when this file is executed directly.
# Importing the functions into a later script will not run the examples.
if __name__ == "__main__":
    main()
