import streamlit as st
import pandas as pd
import json

# --- 1. REGIONAL PRICE PARITY (RPP) DATABASE ---
metro_rpp = {
    "San Francisco, CA": 117.4, "New York, NY": 116.0, "San Diego, CA": 115.2,
    "Los Angeles, CA": 113.1, "Seattle, WA": 111.3, "Washington, DC": 111.0,
    "Boston, MA": 110.5, "Miami, FL": 108.1, "Denver, CO": 105.4,
    "Chicago, IL": 104.2, "Phoenix, AZ": 103.5, "Dallas, TX": 102.0,
    "Austin, TX": 101.5, "Houston, TX": 99.4, "Atlanta, GA": 98.9
}

state_rpp = {
    "AL": 88.8, "AK": 104.8, "AZ": 102.5, "AR": 89.2, "CA": 112.5, "CO": 104.0,
    "CT": 106.1, "DE": 99.0, "FL": 102.1, "GA": 94.5, "HI": 112.4, "ID": 94.2,
    "IL": 100.9, "IN": 91.8, "IA": 89.4, "KS": 90.5, "KY": 89.3, "LA": 90.1,
    "ME": 99.8, "MD": 105.7, "MA": 109.8, "MI": 93.6, "MN": 97.4, "MS": 87.3,
    "MO": 90.7, "MT": 94.3, "NE": 91.5, "NV": 97.5, "NH": 101.8, "NJ": 106.3,
    "NM": 90.6, "NY": 114.8, "NC": 93.3, "ND": 90.4, "OH": 91.7, "OK": 89.1,
    "OR": 102.3, "PA": 97.4, "RI": 102.0, "SC": 93.2, "SD": 88.5, "TN": 91.2,
    "TX": 98.4, "UT": 98.6, "VT": 102.2, "VA": 102.1, "WA": 108.2, "WV": 87.8,
    "WI": 92.5, "WY": 92.2, "DC": 111.0
}


# --- 2. MATH ENGINES ---
def calculate_annual_mortgage(home_value, down_payment_pct=0.20, annual_rate=0.065, years=30):
    # 30-year fixed mortgage formula
    principal = home_value * (1 - down_payment_pct)
    monthly_rate = annual_rate / 12
    num_payments = years * 12

    if principal <= 0:
        return 0

    monthly_payment = principal * (monthly_rate * (1 + monthly_rate) ** num_payments) / (
                (1 + monthly_rate) ** num_payments - 1)
    annual_property_tax = home_value * 0.012  # Estimated national average property tax

    return (monthly_payment * 12) + annual_property_tax


def calculate_progressive_tax(taxable_income, brackets):
    if taxable_income <= 0:
        return 0.0
    total_tax = 0.0
    previous_limit = 0
    for bracket in brackets:
        limit = bracket["limit"]
        rate = bracket["rate"]
        if limit is None or taxable_income <= limit:
            total_tax += (taxable_income - previous_limit) * rate
            break
        else:
            total_tax += (limit - previous_limit) * rate
            previous_limit = limit
    return total_tax


def calculate_total_tax_burden(gross_income, state_abbr, filing_status, taxes_db):
    fica_tax = gross_income * 0.0765
    fed_data = taxes_db["Federal"]
    fed_deduction = fed_data["Standard_Deduction"][filing_status]
    fed_taxable = max(0, gross_income - fed_deduction)
    fed_tax = calculate_progressive_tax(fed_taxable, fed_data[filing_status])

    state_data = taxes_db["States"][state_abbr]
    state_deduction = state_data["Standard_Deduction"][filing_status]
    state_taxable = max(0, gross_income - state_deduction)
    state_tax = calculate_progressive_tax(state_taxable, state_data[filing_status])

    total_taxes = fica_tax + fed_tax + state_tax
    effective_rate = total_taxes / gross_income if gross_income > 0 else 0
    return total_taxes, effective_rate


def find_equivalent_gross(target_net, state_abbr, filing_status, taxes_db):
    low = target_net
    high = target_net * 3
    for _ in range(50):
        mid = (low + high) / 2
        test_tax, _ = calculate_total_tax_burden(mid, state_abbr, filing_status, taxes_db)
        test_net = mid - test_tax
        if abs(test_net - target_net) < 1:
            return mid
        elif test_net < target_net:
            low = mid
        else:
            high = mid
    return mid


# --- 3. DATA LOADING ---
@st.cache_data
def load_databases():
    with open('taxes.json', 'r') as file:
        taxes_db = json.load(file)

    # Load Rent
    df_rent = pd.read_csv('zillow_rent.csv')
    latest_month_rent = df_rent.columns[-1]
    df_rent_clean = df_rent.dropna(subset=[latest_month_rent, 'RegionName'])
    zillow_rent_db = dict(zip(df_rent_clean['RegionName'], df_rent_clean[latest_month_rent]))

    # Load Homes
    df_homes = pd.read_csv('zillow_homes.csv')
    latest_month_home = df_homes.columns[-1]
    df_homes_clean = df_homes.dropna(subset=[latest_month_home, 'RegionName'])
    zillow_home_db = dict(zip(df_homes_clean['RegionName'], df_homes_clean[latest_month_home]))

    # We only want cities that exist in BOTH the rent and home databases to avoid crashes
    available_states = list(taxes_db["States"].keys())
    valid_cities = [city for city in zillow_rent_db.keys() if
                    city in zillow_home_db and str(city).split(', ')[-1] in available_states]
    valid_cities.sort(key=lambda x: (x.split(', ')[-1], x.split(', ')[0]))

    return taxes_db, zillow_rent_db, zillow_home_db, valid_cities


def get_rpp(city_name):
    if city_name in metro_rpp:
        return metro_rpp[city_name]
    state_abbr = city_name.split(', ')[-1]
    return state_rpp.get(state_abbr, 100.0)


# --- 4. USER INTERFACE ---
st.title("Relocation Value Calculator 🏙️")
st.write("Compare the true purchasing power of a job offer using LIVE housing and regional price parity data.")

taxes_db, zillow_rent_db, zillow_home_db, valid_cities = load_databases()

if not valid_cities:
    st.error("No valid cities found. Check database formatting.")
    st.stop()

colA, colB = st.columns(2)
with colA:
    st.markdown("### 1. Tax Bracket")
    filing_status = st.radio("Filing Status:", options=["Single", "Joint"], horizontal=True)
with colB:
    st.markdown("### 2. Housing Strategy")
    housing_preference = st.radio("I plan to:", options=["Rent", "Buy"], horizontal=True)

st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.header("Current Situation")
    current_city = st.selectbox("Current City", options=valid_cities,
                                index=valid_cities.index("San Antonio, TX") if "San Antonio, TX" in valid_cities else 0)
    current_salary = st.number_input("Current Gross Salary ($)", min_value=0, value=150000, step=1000)
with col2:
    st.header("New Offer")
    offer_city = st.selectbox("Offer City", options=valid_cities,
                              index=valid_cities.index("San Diego, CA") if "San Diego, CA" in valid_cities else 1)
    offer_salary = st.number_input("New Offer Salary ($)", min_value=0, value=200000, step=1000)

# --- 5. EXECUTION ---
if st.button("Calculate True Value"):
    with st.spinner("Running cost-of-living algorithms..."):

        c1_rpp = get_rpp(current_city)
        c2_rpp = get_rpp(offer_city)
        c1_state = current_city.split(', ')[-1]
        c2_state = offer_city.split(', ')[-1]

        c1_tax_dollars, c1_effective_rate = calculate_total_tax_burden(current_salary, c1_state, filing_status,
                                                                       taxes_db)
        c1_net = current_salary - c1_tax_dollars

        # ROUTING LOGIC: Rent vs Buy
        if housing_preference == "Rent":
            c1_fixed_housing = zillow_rent_db[current_city] * 12
            c2_fixed_housing = zillow_rent_db[offer_city] * 12
            housing_string_c1 = f"${zillow_rent_db[current_city]:,.2f}/mo rent"
            housing_string_c2 = f"${zillow_rent_db[offer_city]:,.2f}/mo rent"
        else:
            c1_fixed_housing = calculate_annual_mortgage(zillow_home_db[current_city])
            c2_fixed_housing = calculate_annual_mortgage(zillow_home_db[offer_city])
            housing_string_c1 = f"${zillow_home_db[current_city]:,.0f} home (6.5% rate)"
            housing_string_c2 = f"${zillow_home_db[offer_city]:,.0f} home (6.5% rate)"

        c1_discretionary = c1_net - c1_fixed_housing

        purchasing_power_ratio = c2_rpp / c1_rpp
        c2_required_discretionary = c1_discretionary * purchasing_power_ratio

        c2_required_net = c2_required_discretionary + c2_fixed_housing
        target_gross_salary = find_equivalent_gross(c2_required_net, c2_state, filing_status, taxes_db)
        _, c2_effective_rate = calculate_total_tax_burden(offer_salary, c2_state, filing_status, taxes_db)

        # --- 6. OUTPUT UI ---
        st.markdown("---")
        st.markdown(f"### 🏆 The Bottom Line")
        st.markdown(f"To maintain your current standard of living in **{offer_city}**, you need a salary of:")

        st.metric(label=f"Target Salary in {offer_city}", value=f"${target_gross_salary:,.0f}")

        difference = offer_salary - target_gross_salary

        if difference >= 0:
            st.success(
                f"**Great News!** Your offer of **\${offer_salary:,.0f}** is **\${difference:,.0f} HIGHER** than what you need. You will experience a lifestyle upgrade!")
        else:
            st.error(
                f"**Warning:** Your offer of **\${offer_salary:,.0f}** is **\${abs(difference):,.0f} LOWER** than what you actually need. You will take a cut to your standard of living.")

        st.caption(f"**Data Sources Used:**")
        st.caption(
            f"- **Housing Strategy ({housing_preference}):** {current_city} ({housing_string_c1}) | {offer_city} ({housing_string_c2})")
        st.caption(
            f"- **Discretionary Goods (BEA Regional Price Parity):** {current_city} ({c1_rpp}) | {offer_city} ({c2_rpp})")
        st.caption(
            f"- **Calculated Effective Tax Rate (Fed+FICA+State):** {c1_state} ({c1_effective_rate * 100:.1f}%) | {c2_state} ({c2_effective_rate * 100:.1f}%)")