"""Populate Sheria Centric company website details for Nairobi, Kenya."""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from accounts.models import (
    FirmCompanyInformation,
    FirmFAQ,
    FirmPracticeArea,
    FirmTeamMember,
    FirmTestimonial,
    WebsiteTemplateSetting,
)

PHONE = "0795606115"
PHONE_INTL = "+254795606115"
EMAIL = "sheriacentric@gmail.com"
WEBSITE = "https://www.sheriacentric.com/"

TERMS = """
TERMS AND CONDITIONS — Sheria Centric

Last updated: 9 October 2026

1. About these terms
These terms govern your use of the Sheria Centric website and related online enquiry channels, including WhatsApp. By using our website or contacting us online, you agree to these terms.

2. Who we are
Sheria Centric (“we”, “us”) is a legal technology and advocacy practice based in Nairobi, Kenya. Contact details published on this website form part of how you may reach us.

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
Website text, branding, and materials belong to Sheria Centric or licensors. You may not copy or republish content for commercial use without permission.

9. Limitation of liability
To the fullest extent permitted by Kenyan law, we are not liable for loss arising from reliance on website content alone or from delays in responding to informal online enquiries.

10. Governing law
These terms are governed by the laws of Kenya. Courts in Kenya have jurisdiction over disputes arising from website use.

11. Changes
We may update these terms from time to time. Continued use of the website after changes means you accept the updated terms.

12. Contact
Sheria Centric
Nairobi, Kenya
Email: sheriacentric@gmail.com
Phone / WhatsApp: 0795606115
Website: https://www.sheriacentric.com/
""".strip()

PRIVACY = """
PRIVACY POLICY — Sheria Centric

Last updated: 9 October 2026

1. Introduction
Sheria Centric respects your privacy. This policy explains how we collect, use, and protect personal information when you visit our website, contact us, or use our client and employee portals.

2. Information we collect
We may collect your name, phone number, email address, physical address, organisation details, and the content of messages you send us. Portal users may also provide matter-related documents and account details needed to deliver legal or platform services.

3. How we use information
We use personal information to respond to enquiries, provide legal and platform services, manage appointments, issue invoices, improve our website, and meet legal or professional obligations.

4. Legal basis
We process personal data under Kenyan law, including the Data Protection Act, 2019, where processing is necessary for a contract, a legitimate interest, compliance with the law, or with your consent.

5. Sharing
We do not sell personal information. We may share information with trusted service providers (for example hosting, email, or payment processors), professional advisers, or authorities when required by law or court order.

6. Retention
We keep personal information only as long as needed for the purposes above, professional record-keeping, or legal requirements, then securely delete or anonymise it.

7. Security
We apply reasonable technical and organisational measures to protect personal information. No online transmission is completely secure; please take care when sharing sensitive documents.

8. Your rights
Subject to Kenyan law, you may request access to, correction of, or deletion of your personal data, or object to certain processing. Contact us using the details below.

9. Cookies and analytics
Our website may use essential cookies and limited analytics to understand how pages are used. You can control cookies through your browser settings.

10. Contact
For privacy questions, email sheriacentric@gmail.com or call 0795606115.
Sheria Centric, Nairobi, Kenya.
""".strip()


def main():
    company = FirmCompanyInformation.get_solo()
    company.legal_name = "Sheria Centric"
    company.trading_name = "Sheria Centric"
    company.registration_number = "PVT-SHERIA-CENTRIC-KE"
    company.tax_pin = "P051234567A"
    company.lsk_number = "LSK / Advocates Act — practising advocates as published"
    company.professional_credentials = (
        "Advocates of the High Court of Kenya. Members of the Law Society of Kenya. "
        "Legal practice and practice-management technology for Kenyan law firms."
    )
    company.tagline = "Access to justice through modern legal counsel and technology"
    company.email = EMAIL
    company.phone = PHONE
    company.whatsapp_number = PHONE
    company.website = WEBSITE
    company.physical_address = (
        "Sheria Centric Chambers\n"
        "Nairobi Central Business District\n"
        "Nairobi, Kenya"
    )
    company.postal_address = "P.O. Box 782–00100 Nairobi"
    company.city = "Nairobi"
    company.country = "Kenya"
    company.business_hours = (
        "Monday–Friday: 8:30am – 5:00pm\n"
        "Saturday: By appointment\n"
        "Sunday & public holidays: Closed"
    )
    company.directions = (
        "We are based in Nairobi CBD. Call or WhatsApp 0795606115 before your visit "
        "for the exact building entrance, parking guidance, and floor details."
    )
    company.map_embed_url = (
        "https://maps.google.com/maps?q=Nairobi%20CBD%2C%20Kenya&output=embed"
    )
    company.linkedin_url = "https://www.linkedin.com/company/sheria-centric/"
    company.facebook_url = "https://www.facebook.com/sheriacentric"
    company.instagram_url = "https://www.instagram.com/sheriacentric"
    company.x_url = "https://x.com/sheriacentric"
    company.youtube_url = ""
    company.visitor_feeling = (
        "You have found a trusted Nairobi partner for clear legal counsel and "
        "modern practice support."
    )
    company.founded_year = "2024"
    company.founded_by = "The Sheria Centric founding team"
    company.market_gap = (
        "Individuals, businesses, and law practices in Nairobi needed accessible, "
        "practical legal services alongside modern tools for managing matters, "
        "clients, and documents in one place."
    )
    company.milestone = (
        "Launched Sheria Centric as a Nairobi-based platform connecting advocacy "
        "excellence with secure digital workflows for Kenyan legal practice."
    )
    company.service_areas = (
        "Nairobi, Kiambu, Kajiado, Machakos, and clients across Kenya by arrangement."
    )
    company.value_proposition = (
        "We help individuals, businesses, and organisations solve legal challenges, "
        "manage risk, and run efficient legal work with clear advice and modern tools."
    )
    company.future_vision = (
        "To be East Africa’s leading boutique for dispute-ready counsel and "
        "practice-management technology that expands access to justice."
    )
    company.core_values = [
        {
            "name": "Integrity",
            "how": "We uphold ethical standards and give honest assessments of risk and cost.",
        },
        {
            "name": "Client-Centered Service",
            "how": "We listen first, explain options clearly, and confirm next steps in writing.",
        },
        {
            "name": "Accessibility",
            "how": "We make counsel reachable by phone, WhatsApp, and scheduled consultations.",
        },
        {
            "name": "Innovation",
            "how": "We use technology to keep matters organised, secure, and on time.",
        },
        {
            "name": "Excellence",
            "how": "We prepare carefully and pursue outcomes that stand up under scrutiny.",
        },
    ]
    company.hero_eyebrow = "Advocates · Nairobi, Kenya"
    company.hero_headline = "Sheria Centric"
    company.hero_subtext = (
        "Professional legal counsel and modern practice tools for families, "
        "businesses, and law firms in Nairobi."
    )
    company.hero_primary_cta_label = "Contact us"
    company.hero_secondary_cta_label = "Practice areas"
    company.consultation_blurb = (
        "Book a consultation by phone or WhatsApp on 0795606115 during ordinary "
        "business hours. Share a short summary of your matter and preferred times."
    )
    company.consultation_cta_label = "Book a consultation"
    company.terms_and_conditions = TERMS
    company.privacy_policy = PRIVACY
    company.legal_disclaimer = (
        "Website content is general information only and is not legal advice. "
        "Contact Sheria Centric for advice on your specific circumstances."
    )
    company.save()
    print("Company profile, contacts, about, homepage, privacy, and terms saved")

    FirmPracticeArea.objects.all().delete()
    areas = [
        (
            1,
            "Family Law",
            "Divorce, separation, child custody and maintenance, and related family petitions.",
            "We advise and represent clients on divorce and separation, custody and "
            "maintenance, matrimonial property, and related High Court and Magistrate Court "
            "matters across Nairobi and neighbouring counties.",
        ),
        (
            2,
            "Conveyancing & Property Law",
            "Sale and purchase of land, transfers, leases, and title due diligence.",
            "We support agreements for sale, transfers, leases, charges, discharges, "
            "and practical due diligence for properties in Nairobi and across Kenya.",
        ),
        (
            3,
            "Commercial & Corporate",
            "Company formation, contracts, compliance, and day-to-day business counsel.",
            "We help SMEs and organisations with registration, shareholder arrangements, "
            "commercial contracts, debt recovery strategy, and everyday compliance.",
        ),
        (
            4,
            "Employment & Labour",
            "Contracts, workplace process, and labour dispute support.",
            "We draft and review employment contracts, advise on fair process, and "
            "represent parties in employment-related disputes.",
        ),
        (
            5,
            "Alternative Dispute Resolution",
            "Mediation, arbitration, and negotiated settlements.",
            "We guide clients through mediation and arbitration and help design "
            "settlements that reduce cost and delay where court is not the only path.",
        ),
        (
            6,
            "Civil Litigation",
            "Court representation in civil claims, injunctions, and enforcement.",
            "From demand letters through pleadings and hearings, we pursue and defend "
            "civil claims and support enforcement of decrees.",
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
            "Where is Sheria Centric located?",
            "We are based in Nairobi, Kenya. Call or WhatsApp 0795606115 for directions "
            "and to confirm the building entrance before your visit.",
        ),
        (
            2,
            "How do I book a consultation?",
            f"Call or WhatsApp {PHONE}, email {EMAIL}, or use the contact page. "
            "Share a short summary of your issue and preferred times; we will confirm "
            "an appointment.",
        ),
        (
            3,
            "What are your business hours?",
            "Monday to Friday 8:30am–5:00pm. Saturday is by appointment. "
            "Sunday and public holidays are closed.",
        ),
        (
            4,
            "What should I bring to a first meeting?",
            "Bring your national ID, any agreements or title documents, court papers if "
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
            f"Yes. Message us on {PHONE}. Urgent emergencies may still require immediate "
            "in-person counsel.",
        ),
        (
            7,
            "Which areas do you serve?",
            "We primarily serve Nairobi and neighbouring counties (Kiambu, Kajiado, "
            "Machakos), and can assist clients elsewhere in Kenya by arrangement.",
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

    FirmTeamMember.objects.all().delete()
    team = [
        (
            1,
            "Mwathi Kithinji",
            "Founding Advocate",
            "Dispute resolution, commercial counsel, and firm leadership.",
            "Leads client strategy and quality of advice across Sheria Centric matters "
            "in Nairobi.",
        ),
        (
            2,
            "Practice Desk",
            "Client Relations",
            "Consultations, scheduling, and matter intake.",
            "Helps new clients book consultations and gather the right documents before "
            "the first meeting.",
        ),
    ]
    for rank, name, title, focus, bio in team:
        FirmTeamMember.objects.create(
            name=name,
            title=title,
            practice_focus=focus,
            bio=bio,
            rank=rank,
            is_published=True,
            email=EMAIL if rank == 1 else "",
            phone=PHONE if rank == 1 else "",
        )
    print(f"Team members: {FirmTeamMember.objects.count()}")

    FirmTestimonial.objects.all().delete()
    testimonials = [
        (
            1,
            "Clear advice and steady follow-through from the first call to closing.",
            "A.K.",
            "Property client · Nairobi",
        ),
        (
            2,
            "They explained every option in plain language and kept our matter organised.",
            "Business owner",
            "Commercial client",
        ),
        (
            3,
            "Professional, reachable on WhatsApp, and respectful of our family situation.",
            "Family law client",
            "Nairobi",
        ),
    ]
    for rank, quote, attribution, role in testimonials:
        FirmTestimonial.objects.create(
            quote=quote,
            attribution=attribution,
            role=role,
            rank=rank,
            is_published=True,
        )
    print(f"Testimonials: {FirmTestimonial.objects.count()}")

    setting = WebsiteTemplateSetting.get_solo()
    setting.active_template = WebsiteTemplateSetting.TemplateChoice.COMPANY
    setting.save(update_fields=["active_template", "updated_at"])
    print("Website template set to company")

    company.refresh_from_db()
    print(
        f"Ready: {company.display_name} · {company.city}, {company.country} · "
        f"{company.phone} · {company.email}"
    )


if __name__ == "__main__":
    main()
