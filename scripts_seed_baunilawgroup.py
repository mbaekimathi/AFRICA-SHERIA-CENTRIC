"""Populate BAUNILAWGROUP company information for Kiserian, Kajiado County."""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.utils import timezone
from django.utils.text import slugify

from accounts.models import (
    Employee,
    EmployeeBlogPost,
    FirmCompanyInformation,
    FirmFAQ,
    FirmGalleryImage,
    FirmPracticeArea,
    WebsiteTemplateSetting,
)

TERMS = """
TERMS AND CONDITIONS — BAUNILAWGROUP (Bauni Law Group)

Last updated: 19 July 2026

1. About these terms
These terms govern your use of the Bauni Law Group website and related online enquiry channels, including WhatsApp messages sent from our insight articles. By using our website or contacting us online, you agree to these terms.

2. Who we are
Bauni Law Group (“BAUNILAWGROUP”, “we”, “us”) is a law firm based in Kiserian, Kajiado County, Kenya. Contact details published on this website form part of how you may reach us.

3. Information only — not legal advice
Content on this website, including blog articles and FAQs, is general information for public education. It is not legal advice and does not create an advocate–client relationship. Laws change and facts differ; obtain advice tailored to your matter before acting.

4. Enquiries and consultations
Sending a message through our website, email, phone, or WhatsApp is an enquiry only. We are not retained until we accept instructions in writing (or as otherwise agreed) and, where required, engagement terms and fees are confirmed.

5. Confidentiality
Do not send highly sensitive documents through unsecured channels unless we ask you to. We treat genuine client instructions under applicable professional confidentiality rules once engagement begins.

6. Appointments and availability
Office hours and response times may vary. Urgent court or police matters may need immediate in-person counsel; do not rely solely on website messaging for emergencies.

7. Fees
Fee estimates, if given, are indicative until confirmed. Disbursements (filing fees, travel, searches) may be charged separately unless agreed otherwise.

8. Intellectual property
Website text, branding, and materials belong to Bauni Law Group or licensors. You may not copy or republish content for commercial use without permission.

9. Limitation of liability
To the fullest extent permitted by Kenyan law, we are not liable for loss arising from reliance on website content alone or from delays in responding to informal online enquiries.

10. Governing law
These terms are governed by the laws of Kenya. Courts in Kenya have jurisdiction over disputes arising from website use.

11. Changes
We may update these terms from time to time. Continued use of the website after changes means you accept the updated terms.

12. Contact
Bauni Law Group
Along Magadi Road, Kiserian Township, Kajiado County, Kenya
Email: info@baunilawgroup.com
Phone / WhatsApp: +254 795 606 115
Website: https://baunilawgroup.com/
""".strip()


def main():
    company = FirmCompanyInformation.get_solo()
    company.legal_name = "Bauni Law Group"
    company.trading_name = "BAUNILAWGROUP"
    company.registration_number = "PVT-BAUNI-2020-KE"
    company.tax_pin = "P051234567A"
    company.tagline = "Practical counsel for families, land, and business in Kajiado"
    company.email = "info@baunilawgroup.com"
    company.phone = "+254795606115"
    company.website = "https://baunilawgroup.com/"
    company.physical_address = (
        "BAUNILAWGROUP Chambers, Along Magadi Road, "
        "Kiserian Township, Kajiado County, Kenya"
    )
    company.postal_address = "P.O. Box 3023–00208 Ngong"
    company.city = "Kiserian"
    company.country = "Kenya"
    company.visitor_feeling = (
        "Clear, grounded legal guidance for people and businesses building life in Kajiado."
    )
    company.founded_year = "2018"
    company.founded_by = "The Bauni practice team"
    company.market_gap = (
        "Clients around Kiserian, Ngong, and greater Kajiado needed accessible counsel on "
        "land, succession, and small-business disputes without travelling into the city for "
        "every consultation."
    )
    company.milestone = (
        "Expanded a full-service desk in Kiserian supporting conveyancing, family, "
        "employment, and civil litigation for households and SMEs across Kajiado County."
    )
    company.service_areas = (
        "Kiserian, Ngong, Ongata Rongai, Kitengela, Isinya, Kajiado Town, "
        "and surrounding communities in Kajiado County; Nairobi matters by arrangement."
    )
    company.value_proposition = (
        "We help families, landowners, and enterprises in Kajiado resolve legal issues "
        "with clear advice, careful paperwork, and steady court or negotiation support."
    )
    company.future_vision = (
        "To be the trusted neighbourhood law firm for Kajiado—known for integrity on land "
        "and succession matters, and for practical commercial support as the county grows."
    )
    company.core_values = [
        {
            "name": "Integrity",
            "how": "We give honest assessments of risk, cost, and likely outcomes.",
        },
        {
            "name": "Clarity",
            "how": "We explain options in plain language and confirm next steps in writing.",
        },
        {
            "name": "Community",
            "how": "We serve clients where they live and work around Kiserian and Kajiado.",
        },
        {
            "name": "Diligence",
            "how": "We prepare documents carefully and meet filing and hearing deadlines.",
        },
    ]
    company.terms_and_conditions = TERMS
    company.save()
    print("Company profile/contacts/about/terms saved")

    FirmPracticeArea.objects.all().delete()
    areas = [
        (
            1,
            "Conveyancing & Land Law",
            "Sale, purchase, transfers, and due diligence on land in Kajiado and beyond.",
            "We assist with agreements for sale, transfers, charge and discharge of "
            "securities, caution and restriction issues, succession-related transfers, "
            "and practical guidance on title risks common in Kajiado County land markets.",
        ),
        (
            2,
            "Family Law & Succession",
            "Marriage, children matters, and estate administration under Kenyan law.",
            "Our team supports petitions for grant of representation, estate distribution, "
            "family agreements, and sensitive advice for blended families and dependents "
            "in Kiserian and wider Kajiado.",
        ),
        (
            3,
            "Commercial & Corporate",
            "Company formation, contracts, and day-to-day business legal support.",
            "We help SMEs and traders with company registration, shareholder arrangements, "
            "supply and service contracts, debt recovery strategy, and compliance basics "
            "for businesses operating along Magadi Road and across the county.",
        ),
        (
            4,
            "Employment & Labour",
            "Contracts, workplace disputes, and fair process for employers and staff.",
            "We draft and review employment contracts, advise on termination and "
            "disciplinary process, and represent parties in labour-related disputes "
            "before the appropriate forums.",
        ),
        (
            5,
            "Civil Litigation",
            "Court representation in civil claims, injunctions, and enforcement.",
            "From demand letters through pleadings and hearings, we pursue and defend "
            "civil claims including contract disputes, land-related suits, and "
            "enforcement of decrees.",
        ),
        (
            6,
            "Criminal Defence",
            "Representation in criminal complaints and related court appearances.",
            "We advise accused persons and families at police and court stages, with "
            "attention to bail, plea discussions, and trial preparation where required.",
        ),
    ]
    for rank, name, summary, details in areas:
        FirmPracticeArea.objects.create(
            name=name, summary=summary, details=details, rank=rank
        )
    print(f"Practice areas: {FirmPracticeArea.objects.count()}")

    FirmFAQ.objects.all().delete()
    faqs = [
        (
            1,
            "Where is BAUNILAWGROUP located?",
            "Our chambers are along Magadi Road in Kiserian Township, Kajiado County. "
            "Postal address: P.O. Box 3023–00208 Ngong. Call +254 795 606 115 to confirm "
            "directions before your visit.",
        ),
        (
            2,
            "How do I book a consultation?",
            "Call or WhatsApp +254 795 606 115, email info@baunilawgroup.com, or use the "
            "WhatsApp link on our insight articles. Share a short summary of your issue "
            "and preferred times; we will confirm an appointment.",
        ),
        (
            3,
            "Do you handle land transactions in Kajiado?",
            "Yes. Conveyancing and land due diligence are core practice areas, including "
            "agreements for sale, transfers, and title review for properties around "
            "Kiserian, Ngong, Kitengela, and other parts of Kajiado County.",
        ),
        (
            4,
            "What should I bring to a first meeting?",
            "Bring your national ID, any title or agreement documents, court papers if "
            "any, and a written timeline of events. For company matters, bring "
            "registration documents and key contracts.",
        ),
        (
            5,
            "Are website articles legal advice?",
            "No. Our blogs and FAQs are general information only. They do not create a "
            "client relationship. Always seek advice on your specific facts before acting.",
        ),
        (
            6,
            "Do you offer WhatsApp support?",
            "Yes. You may message the firm WhatsApp number published on the website. "
            "Links from articles pre-fill the article title so we can assist faster. "
            "Urgent emergencies may still require immediate in-person counsel.",
        ),
        (
            7,
            "Which languages do you work in?",
            "We primarily work in English and Kiswahili. Let us know your preference "
            "when booking so we can arrange a suitable consultation.",
        ),
        (
            8,
            "How are fees charged?",
            "Fees depend on the nature and urgency of the matter. We discuss estimates "
            "up front where possible. Filing fees and other disbursements are usually "
            "separate unless we agree otherwise in writing.",
        ),
    ]
    for rank, q, a in faqs:
        FirmFAQ.objects.create(question=q, answer=a, rank=rank)
    print(f"FAQs: {FirmFAQ.objects.count()}")

    FirmGalleryImage.objects.all().delete()
    gallery = [
        (
            1,
            "Chambers on Magadi Road",
            "BAUNILAWGROUP reception and client waiting area in Kiserian Township.",
        ),
        (
            2,
            "Client consultation room",
            "Private meeting space for land, family, and business consultations.",
        ),
        (
            3,
            "Kajiado community desk",
            "Walk-in support for residents of Kiserian, Ngong, and nearby towns.",
        ),
        (
            4,
            "Document preparation bay",
            "Where agreements, petitions, and conveyancing packs are prepared.",
        ),
    ]
    for rank, title, caption in gallery:
        FirmGalleryImage.objects.create(title=title, caption=caption, rank=rank)
    print(f"Gallery items: {FirmGalleryImage.objects.count()}")

    setting = WebsiteTemplateSetting.get_solo()
    setting.active_template = WebsiteTemplateSetting.TemplateChoice.COMPANY
    setting.save(update_fields=["active_template", "updated_at"])
    print("Website template set to company")

    author = (
        Employee.objects.filter(login_code="000000").first()
        or Employee.objects.filter(status=Employee.Status.ACTIVE).first()
    )
    mwathi = Employee.objects.filter(login_code="666666").first()

    # Ensure signature blogs are published for the firm site
    now = timezone.now()
    blog_specs = [
        (
            author,
            "How to register a private limited company in Kenya",
            "register-private-limited-company-kenya",
            "register company Kenya",
        ),
        (
            mwathi or author,
            "Employment contracts in Kenya: what every employer must include",
            "employment-contracts-kenya-employer-guide",
            "employment contracts Kenya",
        ),
        (
            author,
            "Buying land in Kajiado: due diligence tips for Kiserian buyers",
            "buying-land-kajiado-kiserian-due-diligence",
            "buying land Kajiado",
        ),
    ]

    land_body = """
Buying land in Kajiado County—especially around Kiserian, Ngong, and Kitengela—can be a strong investment. It can also go wrong quickly when title, occupancy, or seller authority is unclear.

This guide sets out practical due diligence steps BAUNILAWGROUP recommends before you pay a deposit or sign an agreement for sale.

## Confirm what you are buying

Ask for:

- a current title search
- copies of the title or allotment documents
- seller identification matching the registered owner
- any spousal or third-party consents that may be required

If the land is held under a company or group structure, verify who has authority to sell.

## Walk the ground

Visit the parcel with a surveyor or trusted local guide. Check beacons, access roads, neighbouring uses, and whether anyone is in occupation. Occupied land is not automatically unsellable—but it changes risk and process.

## Use a written agreement for sale

A clear agreement should state the price, deposit, completion timeline, what documents the seller must deliver, and what happens if either side defaults. Avoid informal cash deals that leave you without remedies.

## Budget for conveyancing costs

Beyond the purchase price, plan for legal fees, stamp duty where applicable, registration fees, and search costs. Ask for an estimate early.

## When to instruct counsel in Kiserian

Instruct a lawyer before you pay significant money. Early advice on buying land Kajiado parcels often costs less than fixing a defective transfer later.

BAUNILAWGROUP assists buyers and sellers along Magadi Road and across Kajiado with agreements, searches, and registration follow-through.
""".strip()

    for person, title, slug, keyword in blog_specs:
        if not person:
            continue
        post = EmployeeBlogPost.objects.filter(slug=slug).first()
        if slug == "buying-land-kajiado-kiserian-due-diligence":
            if post:
                post.delete()
            post = EmployeeBlogPost(
                author=person,
                title=title,
                slug=slug,
                excerpt=(
                    "Practical due diligence for buyers around Kiserian and Kajiado: "
                    "title searches, site visits, agreements for sale, and when to instruct counsel."
                ),
                body=land_body,
                meta_title="Buying land in Kajiado: Kiserian due diligence",
                meta_description=(
                    "Due diligence tips for buying land in Kajiado County and Kiserian—"
                    "title checks, occupation, agreements for sale, and conveyancing costs."
                ),
                focus_keyword=keyword,
                tags="land law, conveyancing, Kajiado, Kiserian",
                status=EmployeeBlogPost.Status.PUBLISHED,
                submitted_at=now,
                published_at=now,
                approved_at=now,
                approved_by=person,
            )
            post.save()
        elif post:
            post.status = EmployeeBlogPost.Status.PUBLISHED
            if not post.published_at:
                post.published_at = now
            if not post.submitted_at:
                post.submitted_at = now
            post.approved_by = post.approved_by or person
            post.approved_at = post.approved_at or now
            post.save()
        print("Blog ready:", slug)

    print(
        "Done.",
        "published blogs:",
        EmployeeBlogPost.objects.filter(status="published").count(),
        "firm:",
        company.display_name,
        company.city,
    )


if __name__ == "__main__":
    main()
