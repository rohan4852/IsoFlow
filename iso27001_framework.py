"""
ISO 27001:2022 Internal Audit Readiness & Gap Assessment Matrix

Complete reference schema containing:
- Clauses 4–10 (Management System Requirements)
- Annex A Controls (5–8: Organizational, People, Physical, Technological)

This module provides immutable, stateless reference data for gap analysis.
All data is loaded into volatile memory (zero-retention architecture).

Source: ISO 27001:2022 Internal Audit Checklist (CIC)
"""

from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class ControlRequirement:
    """
    Immutable representation of an ISO 27001:2022 control or clause requirement.
    
    Attributes:
        id: Control identifier (e.g., "4.1", "A.5.15")
        category: "Clause" for management system, "Annex A" for controls
        section: Logical section grouping (e.g., "Context of the Organisation")
        name: Short name of the control/clause
        requirement: Official requirement description
    """
    id: str
    category: str  # "Clause" | "Annex A"
    section: str
    name: str
    requirement: str


# ============================================================================
# ISO 27001:2022 COMPLETE FRAMEWORK
# ============================================================================

ISO27001_FRAMEWORK: List[ControlRequirement] = [
    
    # ========================================================================
    # CLAUSES 4-10: MANAGEMENT SYSTEM REQUIREMENTS
    # ========================================================================
    
    # --- CLAUSE 4: CONTEXT OF THE ORGANISATION ---
    ControlRequirement(
        id="4.1",
        category="Clause",
        section="Context of the Organisation",
        name="Understanding the organization and its context",
        requirement="The organisation shall determine external and internal issues relevant to its purpose and that affect its ability to achieve the intended outcome(s) of its information security management system."
    ),
    ControlRequirement(
        id="4.2",
        category="Clause",
        section="Context of the Organisation",
        name="Understanding the needs and expectations of interested parties",
        requirement="The organisation shall determine the interested parties that are relevant to the information security management system and the requirements of these interested parties."
    ),
    ControlRequirement(
        id="4.3",
        category="Clause",
        section="Context of the Organisation",
        name="Determining the scope of the information security management system",
        requirement="The organisation shall determine the boundaries and applicability of the information security management system to establish its scope. The scope shall be available as documented information."
    ),
    ControlRequirement(
        id="4.4",
        category="Clause",
        section="Context of the Organisation",
        name="Information security management system",
        requirement="The organisation shall establish, implement, maintain and continually improve an information security management system, including the necessary processes, considering the context determined in clauses 4.1 and 4.2."
    ),
    
    # --- CLAUSE 5: LEADERSHIP ---
    ControlRequirement(
        id="5.1",
        category="Clause",
        section="Leadership",
        name="Leadership and commitment",
        requirement="Top management shall demonstrate leadership and commitment with respect to the information security management system by: taking accountability for the effectiveness of the ISMS; ensuring the information security policy and objectives are established; ensuring integration of ISMS requirements into organisation processes."
    ),
    ControlRequirement(
        id="5.2",
        category="Clause",
        section="Leadership",
        name="Information security policy",
        requirement="Top management shall establish an information security policy that is appropriate to the purpose of the organisation, provides a framework for setting information security objectives, and includes a commitment to satisfy applicable requirements related to information security."
    ),
    ControlRequirement(
        id="5.3",
        category="Clause",
        section="Leadership",
        name="Organizational roles, responsibilities and authorities",
        requirement="Top management shall ensure that the responsibilities and authorities for roles relevant to information security are assigned and communicated throughout the organisation."
    ),
    
    # --- CLAUSE 6: PLANNING ---
    ControlRequirement(
        id="6.1",
        category="Clause",
        section="Planning",
        name="Actions to address risks and opportunities",
        requirement="The organisation shall determine the information security risks and opportunities and implement measures to address the risk treatment and the risks and opportunities, taking into account the risk assessment results."
    ),
    ControlRequirement(
        id="6.2",
        category="Clause",
        section="Planning",
        name="Information security objectives and planning to achieve them",
        requirement="The organisation shall establish information security objectives at relevant functions and levels, taking into account compliance obligations. Objectives shall be documented, and communicated to relevant personnel, with plans to achieve them and progress monitored."
    ),
    
    # --- CLAUSE 7: SUPPORT ---
    ControlRequirement(
        id="7.1",
        category="Clause",
        section="Support",
        name="Resources",
        requirement="The organisation shall determine and provide the resources needed for the establishment, implementation, maintenance and continual improvement of the information security management system."
    ),
    ControlRequirement(
        id="7.2",
        category="Clause",
        section="Support",
        name="Competence",
        requirement="The organisation shall determine the necessary competence of person(s) doing work under its control that affects its information security performance, ensure such persons are competent, and maintain records."
    ),
    ControlRequirement(
        id="7.3",
        category="Clause",
        section="Support",
        name="Awareness",
        requirement="The organisation shall ensure that persons doing work under the organisation's control are aware of the information security policy, their contribution to the effectiveness of the ISMS, and the implications of not conforming with its requirements."
    ),
    ControlRequirement(
        id="7.4",
        category="Clause",
        section="Support",
        name="Communication",
        requirement="The organisation shall determine the need for internal and external communication relevant to the information security management system, including on what it will communicate, when, to whom and how."
    ),
    ControlRequirement(
        id="7.5",
        category="Clause",
        section="Support",
        name="Documented information",
        requirement="The organisation shall determine and manage the information and technology needed to support the operation of the ISMS and to ensure conformity with its requirements."
    ),
    
    # --- CLAUSE 8: OPERATION ---
    ControlRequirement(
        id="8.1",
        category="Clause",
        section="Operation",
        name="Operational planning and control",
        requirement="The organisation shall establish the processes needed to meet the requirements of the ISMS through the implementation of controls. Changes to the ISMS shall be planned and controlled to maintain the effectiveness of the system."
    ),
    ControlRequirement(
        id="8.2",
        category="Clause",
        section="Operation",
        name="Assessment of information security risks",
        requirement="The organisation shall perform information security risk assessments at planned intervals and when significant changes to the organisation, its processes, systems or operating environment occur."
    ),
    ControlRequirement(
        id="8.3",
        category="Clause",
        section="Operation",
        name="Implementation of information security controls",
        requirement="The organisation shall define a risk treatment plan and Statement of Applicability, implement identified controls in accordance with the risk assessment results and maintain records."
    ),
    
    # --- CLAUSE 9: PERFORMANCE EVALUATION ---
    ControlRequirement(
        id="9.1",
        category="Clause",
        section="Performance Evaluation",
        name="Monitoring, measurement, analysis and evaluation",
        requirement="The organisation shall monitor and measure the characteristics of its processes to the extent necessary to verify conformity and effectiveness, analyse the results and maintain documented information."
    ),
    ControlRequirement(
        id="9.2",
        category="Clause",
        section="Performance Evaluation",
        name="Internal audit",
        requirement="The organisation shall conduct internal audits at planned intervals to provide information on whether the ISMS conforms to its own requirements and those of the standard, and is effectively implemented and maintained."
    ),
    ControlRequirement(
        id="9.3",
        category="Clause",
        section="Performance Evaluation",
        name="Management review",
        requirement="Top management shall review the ISMS at planned intervals to ensure its continuing suitability, adequacy, effectiveness and alignment with the strategic direction of the organisation."
    ),
    
    # --- CLAUSE 10: IMPROVEMENT ---
    ControlRequirement(
        id="10.1",
        category="Clause",
        section="Improvement",
        name="Continual improvement",
        requirement="The organisation shall continually improve the suitability, adequacy and effectiveness of the information security management system."
    ),
    ControlRequirement(
        id="10.2",
        category="Clause",
        section="Improvement",
        name="Nonconformity and corrective action",
        requirement="The organisation shall deal with nonconformities by taking corrective actions proportionate to the impacts. It shall maintain records of nonconformities and corrective actions taken."
    ),
    
    # ========================================================================
    # ANNEX A (5): ORGANIZATIONAL CONTROLS
    # ========================================================================
    
    ControlRequirement(
        id="A.5.1",
        category="Annex A",
        section="Organizational Controls",
        name="Policies for information security",
        requirement="A set of information security policies relevant to interested parties shall be established to direct and support the information security management system."
    ),
    ControlRequirement(
        id="A.5.2",
        category="Annex A",
        section="Organizational Controls",
        name="Information security roles and responsibilities",
        requirement="Roles and responsibilities for information security shall be defined and allocated to relevant personnel and shall be communicated to all interested parties."
    ),
    ControlRequirement(
        id="A.5.3",
        category="Annex A",
        section="Organizational Controls",
        name="Segregation of duties",
        requirement="Conflicting duties and areas of responsibility shall be segregated to reduce opportunities for unauthorised or unintentional modification or misuse of the organisation's information and information processing facilities."
    ),
    ControlRequirement(
        id="A.5.4",
        category="Annex A",
        section="Organizational Controls",
        name="Management responsibilities",
        requirement="Management shall ensure that all personnel are applying information security in accordance with the established policies and procedures of the organisation."
    ),
    ControlRequirement(
        id="A.5.5",
        category="Annex A",
        section="Organizational Controls",
        name="Contact with authorities",
        requirement="Appropriate contacts with relevant authorities shall be established and maintained to ensure effective communication regarding information security incidents and obligations."
    ),
    ControlRequirement(
        id="A.5.6",
        category="Annex A",
        section="Organizational Controls",
        name="Contact with special interest groups",
        requirement="Contact with special interest groups, security forums and professional associations shall be established and maintained to stay informed of emerging threats and best practices."
    ),
    ControlRequirement(
        id="A.5.7",
        category="Annex A",
        section="Organizational Controls",
        name="Threat intelligence",
        requirement="Information relating to information security threats shall be collected and analysed to identify relevant threats and inform risk assessment and treatment decisions."
    ),
    ControlRequirement(
        id="A.5.8",
        category="Annex A",
        section="Organizational Controls",
        name="Information security in project management",
        requirement="Information security shall be integrated into project management activities to ensure that information security risks are properly managed across all project phases."
    ),
    ControlRequirement(
        id="A.5.9",
        category="Annex A",
        section="Organizational Controls",
        name="Inventory of information and other associated assets",
        requirement="An inventory shall be developed and maintained of information and other associated assets, with identification of owners responsible for their management."
    ),
    ControlRequirement(
        id="A.5.10",
        category="Annex A",
        section="Organizational Controls",
        name="Acceptable use of information and other associated assets",
        requirement="Rules for the acceptable use and procedures for handling information and other associated assets shall be defined, documented, and implemented for all personnel and interested parties."
    ),
    ControlRequirement(
        id="A.5.11",
        category="Annex A",
        section="Organizational Controls",
        name="Return of assets",
        requirement="All assets belonging to the organisation in the possession of personnel and other interested parties shall be returned upon change to or termination of their employment, contract or agreement."
    ),
    ControlRequirement(
        id="A.5.12",
        category="Annex A",
        section="Organizational Controls",
        name="Classification of information",
        requirement="Information shall be classified based on legal requirements, value, criticality, and sensitivity to support appropriate handling and protection measures."
    ),
    ControlRequirement(
        id="A.5.13",
        category="Annex A",
        section="Organizational Controls",
        name="Labelling of information",
        requirement="A set of procedures for labelling of information shall be defined, documented, and implemented in accordance with the information classification scheme."
    ),
    ControlRequirement(
        id="A.5.14",
        category="Annex A",
        section="Organizational Controls",
        name="Information transfer",
        requirement="Rules, procedures or agreements shall be defined and implemented for all types of information transfer facilities within the organisation and between the organisation and external parties."
    ),
    ControlRequirement(
        id="A.5.15",
        category="Annex A",
        section="Organizational Controls",
        name="Access control",
        requirement="Rules shall be defined and documented to control physical and logical access to information based on the principle of least privilege and need-to-know basis."
    ),
    ControlRequirement(
        id="A.5.16",
        category="Annex A",
        section="Organizational Controls",
        name="Identity management",
        requirement="Management of identities for their full life cycle, from registration through deactivation, shall be controlled and documented to ensure proper access governance."
    ),
    ControlRequirement(
        id="A.5.17",
        category="Annex A",
        section="Organizational Controls",
        name="Authentication information",
        requirement="Allocation and management of authentication information, such as usernames and passwords, shall be controlled by a management process that includes advising personnel on appropriate handling."
    ),
    ControlRequirement(
        id="A.5.18",
        category="Annex A",
        section="Organizational Controls",
        name="Access rights",
        requirement="Access rights to information and other assets shall be provisioned, reviewed, and monitored in accordance with the access control policy and relevant rules."
    ),
    ControlRequirement(
        id="A.5.19",
        category="Annex A",
        section="Organizational Controls",
        name="Information security in supplier relationships",
        requirement="Processes and procedures shall be defined and implemented to manage information security risks associated with the use of supplier products or services."
    ),
    ControlRequirement(
        id="A.5.20",
        category="Annex A",
        section="Organizational Controls",
        name="Addressing information security within supplier agreements",
        requirement="Information security requirements shall be established and agreed upon in supplier relationships to ensure suppliers meet the organisation's security expectations."
    ),
    ControlRequirement(
        id="A.5.21",
        category="Annex A",
        section="Organizational Controls",
        name="Managing information security in the ICT supply chain",
        requirement="Processes and procedures shall be defined to manage information security risks associated with ICT products and services supply chain."
    ),
    ControlRequirement(
        id="A.5.22",
        category="Annex A",
        section="Organizational Controls",
        name="Monitoring, review and change management of supplier services",
        requirement="Regular monitoring, review, and evaluation of changes in supplier information security practices shall be performed to ensure ongoing compliance."
    ),
    ControlRequirement(
        id="A.5.23",
        category="Annex A",
        section="Organizational Controls",
        name="Information security for use of cloud services",
        requirement="Processes for the acquisition, use, management, and exit from cloud services shall be established to ensure compliance with organisational information security requirements."
    ),
    ControlRequirement(
        id="A.5.24",
        category="Annex A",
        section="Organizational Controls",
        name="Information security incident management planning and preparation",
        requirement="Processes, roles and responsibilities for management of information security incidents shall be defined, documented, implemented and communicated."
    ),
    ControlRequirement(
        id="A.5.25",
        category="Annex A",
        section="Organizational Controls",
        name="Assessment and decision on information security events",
        requirement="Information security events shall be assessed to determine if they are to be categorised as information security incidents for management and response."
    ),
    ControlRequirement(
        id="A.5.26",
        category="Annex A",
        section="Organizational Controls",
        name="Response to information security incidents",
        requirement="Documented and implemented procedures shall define appropriate response to information security incidents in a timely manner."
    ),
    ControlRequirement(
        id="A.5.27",
        category="Annex A",
        section="Organizational Controls",
        name="Learning from information security incidents",
        requirement="Knowledge gained from information security incidents shall be used to strengthen and improve controls and prevent recurrence."
    ),
    ControlRequirement(
        id="A.5.28",
        category="Annex A",
        section="Organizational Controls",
        name="Collection of evidence",
        requirement="Procedures shall be established and implemented for identification, collection, acquisition, and preservation of evidence relating to information security events."
    ),
    ControlRequirement(
        id="A.5.29",
        category="Annex A",
        section="Organizational Controls",
        name="Information security during disruption",
        requirement="A plan shall be developed to maintain information security at an appropriate level during disruption to business operations."
    ),
    ControlRequirement(
        id="A.5.30",
        category="Annex A",
        section="Organizational Controls",
        name="ICT readiness for business continuity",
        requirement="Processes shall be implemented so the organisation can continue operations in case of a disruption affecting ICT systems and services."
    ),
    ControlRequirement(
        id="A.5.31",
        category="Annex A",
        section="Organizational Controls",
        name="Legal, statutory, regulatory and contractual requirements",
        requirement="Legal, statutory, regulatory and contractual requirements relating to information security shall be identified, documented and kept up to date."
    ),
    ControlRequirement(
        id="A.5.32",
        category="Annex A",
        section="Organizational Controls",
        name="Intellectual property rights",
        requirement="Appropriate procedures shall be implemented to protect intellectual property rights within the organisation."
    ),
    ControlRequirement(
        id="A.5.33",
        category="Annex A",
        section="Organizational Controls",
        name="Protection of records",
        requirement="Records shall be stored and protected such that they are protected from loss, destruction, falsification, unauthorised access and unauthorised release."
    ),
    ControlRequirement(
        id="A.5.34",
        category="Annex A",
        section="Organizational Controls",
        name="Privacy and protection of personal identifiable information (PII)",
        requirement="The organisation shall identify and meet relevant requirements regarding preservation of privacy and protection of personal identifiable information."
    ),
    ControlRequirement(
        id="A.5.35",
        category="Annex A",
        section="Organizational Controls",
        name="Independent review of information security",
        requirement="Independent reviews shall be conducted at planned intervals, or when significant changes occur, of the organisational approach to managing information security."
    ),
    ControlRequirement(
        id="A.5.36",
        category="Annex A",
        section="Organizational Controls",
        name="Compliance with policies, rules and standards for information security",
        requirement="Organisational compliance with its information security policy and topic-specific policies, rules and standards shall be regularly reviewed."
    ),
    ControlRequirement(
        id="A.5.37",
        category="Annex A",
        section="Organizational Controls",
        name="Documented operating procedures",
        requirement="Documented procedures for information processing activities and facilities shall be established, maintained and made available to relevant personnel."
    ),
    
    # ========================================================================
    # ANNEX A (6): PEOPLE CONTROLS
    # ========================================================================
    
    ControlRequirement(
        id="A.6.1",
        category="Annex A",
        section="People Controls",
        name="Screening",
        requirement="Background checks shall be conducted on all candidates prior to joining the organisation and on an ongoing basis in accordance with relevant laws, regulations and ethics."
    ),
    ControlRequirement(
        id="A.6.2",
        category="Annex A",
        section="People Controls",
        name="Terms and conditions of employment",
        requirement="Personnel and organisational responsibilities for information security shall be defined and documented in employment contractual agreements and terms."
    ),
    ControlRequirement(
        id="A.6.3",
        category="Annex A",
        section="People Controls",
        name="Information security awareness, education and training",
        requirement="Personnel and other relevant interested parties shall receive appropriate information security awareness, education and training, and updates on policies and procedures."
    ),
    ControlRequirement(
        id="A.6.4",
        category="Annex A",
        section="People Controls",
        name="Disciplinary process",
        requirement="A formalised process shall be established and communicated to take actions against personnel and other relevant interested parties who violate information security policies."
    ),
    ControlRequirement(
        id="A.6.5",
        category="Annex A",
        section="People Controls",
        name="Responsibilities after termination or change of employment",
        requirement="Responsibilities and duties that remain after termination or change of employment shall be defined, enforced and communicated to relevant personnel and interested parties."
    ),
    ControlRequirement(
        id="A.6.6",
        category="Annex A",
        section="People Controls",
        name="Confidentiality or non-disclosure agreements",
        requirement="Confidentiality or non-disclosure agreements shall be documented and regularly reviewed and signed by personnel and other relevant parties as per organisational needs."
    ),
    ControlRequirement(
        id="A.6.7",
        category="Annex A",
        section="People Controls",
        name="Remote working",
        requirement="Security measures shall be implemented when personnel are working remotely such that information accessed, processed or stored outside the organisation's premises is protected."
    ),
    ControlRequirement(
        id="A.6.8",
        category="Annex A",
        section="People Controls",
        name="Information security event reporting",
        requirement="A method shall be provided by which personnel can report observed or suspected information security events through appropriate channels in a timely manner."
    ),
    
    # ========================================================================
    # ANNEX A (7): PHYSICAL CONTROLS
    # ========================================================================
    
    ControlRequirement(
        id="A.7.1",
        category="Annex A",
        section="Physical Controls",
        name="Physical security perimeters",
        requirement="Security perimeters shall be defined and used to protect areas that contain information and information processing facilities and other associated assets."
    ),
    ControlRequirement(
        id="A.7.2",
        category="Annex A",
        section="Physical Controls",
        name="Physical entry",
        requirement="Secure areas shall be protected with appropriate physical entry controls and access points to restrict unauthorised access."
    ),
    ControlRequirement(
        id="A.7.3",
        category="Annex A",
        section="Physical Controls",
        name="Securing offices, rooms and facilities",
        requirement="Physical security for offices, rooms and facilities shall be designed and implemented to protect information and information processing facilities."
    ),
    ControlRequirement(
        id="A.7.4",
        category="Annex A",
        section="Physical Controls",
        name="Physical security monitoring",
        requirement="Premises shall be continuously monitored for unauthorised physical access to prevent compromise of information and facilities."
    ),
    ControlRequirement(
        id="A.7.5",
        category="Annex A",
        section="Physical Controls",
        name="Protecting against physical and environmental threats",
        requirement="Infrastructure shall be designed and implemented to protect against physical and environmental threats such as natural disasters and other hazards."
    ),
    ControlRequirement(
        id="A.7.6",
        category="Annex A",
        section="Physical Controls",
        name="Working in secure areas",
        requirement="Security measures shall be designed and implemented for working in secure areas to ensure information is protected during use."
    ),
    ControlRequirement(
        id="A.7.7",
        category="Annex A",
        section="Physical Controls",
        name="Clear desk and clear screen",
        requirement="Clear desk rules for papers and removable storage media, and clear screen rules for information processing facilities shall be defined and enforced."
    ),
    ControlRequirement(
        id="A.7.8",
        category="Annex A",
        section="Physical Controls",
        name="Equipment siting and protection",
        requirement="Equipment shall be securely sited and protected against threats and environmental hazards to ensure availability and integrity of information."
    ),
    ControlRequirement(
        id="A.7.9",
        category="Annex A",
        section="Physical Controls",
        name="Security of assets off-premises",
        requirement="Assets that are stored or transported off-site shall be protected against unauthorised access, theft or damage."
    ),
    ControlRequirement(
        id="A.7.10",
        category="Annex A",
        section="Physical Controls",
        name="Storage media",
        requirement="Storage media shall be managed through their life cycle of acquisition, use, transportation and disposal in accordance with classification scheme and handling requirements."
    ),
    ControlRequirement(
        id="A.7.11",
        category="Annex A",
        section="Physical Controls",
        name="Supporting utilities",
        requirement="Information processing facilities shall be protected from power failures and other disruptions caused by failures in supporting utilities."
    ),
    ControlRequirement(
        id="A.7.12",
        category="Annex A",
        section="Physical Controls",
        name="Cabling security",
        requirement="Cables carrying power, data or supporting information services shall be protected from interception, interference and damage."
    ),
    ControlRequirement(
        id="A.7.13",
        category="Annex A",
        section="Physical Controls",
        name="Equipment maintenance",
        requirement="Equipment shall be maintained correctly to ensure the availability, integrity and confidentiality of information and systems."
    ),
    ControlRequirement(
        id="A.7.14",
        category="Annex A",
        section="Physical Controls",
        name="Secure disposal or re-use of media",
        requirement="Equipment containing storage media shall be verified to ensure that sensitive data and licensed software has been securely removed prior to disposal or re-use."
    ),
    
    # ========================================================================
    # ANNEX A (8): TECHNOLOGICAL CONTROLS
    # ========================================================================
    
    ControlRequirement(
        id="A.8.1",
        category="Annex A",
        section="Technological Controls",
        name="User end point devices",
        requirement="Information stored on, processed by or accessible via user end point devices shall be protected against unauthorised access and malware."
    ),
    ControlRequirement(
        id="A.8.2",
        category="Annex A",
        section="Technological Controls",
        name="Privileged access rights",
        requirement="The use of privileged access rights shall be restricted and managed to prevent unauthorised access to information systems and resources."
    ),
    ControlRequirement(
        id="A.8.3",
        category="Annex A",
        section="Technological Controls",
        name="Information access restriction",
        requirement="Access to information and other associated assets shall be restricted in accordance with the organisation's access control policy based on business and security requirements."
    ),
    ControlRequirement(
        id="A.8.4",
        category="Annex A",
        section="Technological Controls",
        name="Access to source code",
        requirement="Read and write access to source code, development tools and software libraries shall be managed to prevent unauthorised access and modification."
    ),
    ControlRequirement(
        id="A.8.5",
        category="Annex A",
        section="Technological Controls",
        name="Secure authentication",
        requirement="Secure authentication technologies and procedures shall be implemented based on access restrictions and the organisation's access control policy."
    ),
    ControlRequirement(
        id="A.8.6",
        category="Annex A",
        section="Technological Controls",
        name="Capacity management",
        requirement="The use of resources shall be monitored, measured and adjusted to ensure optimal performance and to manage capacity in accordance with forecast requirements."
    ),
    ControlRequirement(
        id="A.8.7",
        category="Annex A",
        section="Technological Controls",
        name="Protection against malware",
        requirement="Malware protection shall be implemented and kept up to date on all systems, supported by user awareness, to prevent infection and spread."
    ),
    ControlRequirement(
        id="A.8.8",
        category="Annex A",
        section="Technological Controls",
        name="Management of technical vulnerabilities",
        requirement="Information about technical vulnerabilities shall be obtained, the organisation's exposure evaluated, and appropriate measures taken to address identified vulnerabilities."
    ),
    ControlRequirement(
        id="A.8.9",
        category="Annex A",
        section="Technological Controls",
        name="Configuration management",
        requirement="Configurations including security configurations of hardware, software, services and networks shall be established, documented, implemented, monitored and reviewed."
    ),
    ControlRequirement(
        id="A.8.10",
        category="Annex A",
        section="Technological Controls",
        name="Information deletion",
        requirement="Information stored in information systems, devices or other storage media shall be securely deleted when the information is no longer required."
    ),
    ControlRequirement(
        id="A.8.11",
        category="Annex A",
        section="Technological Controls",
        name="Data masking",
        requirement="Data shall be masked as appropriate and in accordance with the organisation's access control policy to protect sensitive information."
    ),
    ControlRequirement(
        id="A.8.12",
        category="Annex A",
        section="Technological Controls",
        name="Data leakage prevention",
        requirement="Measures shall be applied to systems, networks and devices that process, store or transmit sensitive data to prevent leakage of data."
    ),
    ControlRequirement(
        id="A.8.13",
        category="Annex A",
        section="Technological Controls",
        name="Information backup",
        requirement="Backup copies of information, software and systems shall be maintained and regularly tested to ensure recovery capability."
    ),
    ControlRequirement(
        id="A.8.14",
        category="Annex A",
        section="Technological Controls",
        name="Redundancy of information processing facilities",
        requirement="Sufficient redundancy in information processing facilities shall be implemented to meet availability and resilience requirements."
    ),
    ControlRequirement(
        id="A.8.15",
        category="Annex A",
        section="Technological Controls",
        name="Logging",
        requirement="Logs recording user activities, exceptions, faults and other security-relevant events shall be produced, stored, protected and analysed."
    ),
    ControlRequirement(
        id="A.8.16",
        category="Annex A",
        section="Technological Controls",
        name="Monitoring activities",
        requirement="Networks, systems and applications shall be monitored for unusual behaviour and potential information security events requiring investigation."
    ),
    ControlRequirement(
        id="A.8.17",
        category="Annex A",
        section="Technological Controls",
        name="Clock synchronisation",
        requirement="Clocks of information processing systems shall be synchronised to an agreed accurate time source to ensure correct logging and audit trails."
    ),
    ControlRequirement(
        id="A.8.18",
        category="Annex A",
        section="Technological Controls",
        name="Use of privileged utility programs",
        requirement="The use of utility programs that can override system and application controls shall be restricted and monitored."
    ),
    ControlRequirement(
        id="A.8.19",
        category="Annex A",
        section="Technological Controls",
        name="Installation of software on operational systems",
        requirement="Procedures shall be implemented to securely manage the installation of software on operational systems to prevent unauthorised or malicious installation."
    ),
    ControlRequirement(
        id="A.8.20",
        category="Annex A",
        section="Technological Controls",
        name="Networks security",
        requirement="Networks and network devices shall be secured, managed and controlled to protect information in systems and applications from unauthorised access."
    ),
    ControlRequirement(
        id="A.8.21",
        category="Annex A",
        section="Technological Controls",
        name="Security of network services",
        requirement="Security mechanisms, service levels and service requirements of network services shall be implemented and monitored to protect information in transit."
    ),
    ControlRequirement(
        id="A.8.22",
        category="Annex A",
        section="Technological Controls",
        name="Segregation of networks",
        requirement="Groups of information services, users and information systems shall be segregated in the organisation's networks based on trust levels and security requirements."
    ),
    ControlRequirement(
        id="A.8.23",
        category="Annex A",
        section="Technological Controls",
        name="Web filtering",
        requirement="Access to external websites shall be managed to reduce exposure to malicious content and unauthorised information."
    ),
    ControlRequirement(
        id="A.8.24",
        category="Annex A",
        section="Technological Controls",
        name="Use of cryptography",
        requirement="Rules for the effective use of cryptography shall be defined and implemented, including cryptographic key management and protection."
    ),
    ControlRequirement(
        id="A.8.25",
        category="Annex A",
        section="Technological Controls",
        name="Secure development lifecycle",
        requirement="Rules for the secure development of software and systems shall be established and applied to all development activities."
    ),
    ControlRequirement(
        id="A.8.26",
        category="Annex A",
        section="Technological Controls",
        name="Application security requirements",
        requirement="Information security requirements shall be identified and documented when developing or acquiring applications to ensure secure design."
    ),
    ControlRequirement(
        id="A.8.27",
        category="Annex A",
        section="Technological Controls",
        name="Secure system architecture and engineering principles",
        requirement="Principles for engineering secure systems shall be documented and applied to all information system development activities."
    ),
    ControlRequirement(
        id="A.8.28",
        category="Annex A",
        section="Technological Controls",
        name="Secure coding",
        requirement="Secure coding principles shall be applied to software development to prevent vulnerabilities and ensure code integrity."
    ),
    ControlRequirement(
        id="A.8.29",
        category="Annex A",
        section="Technological Controls",
        name="Security testing in development and acceptance",
        requirement="Processes for security testing shall be defined and implemented within the development life cycle and before system acceptance."
    ),
    ControlRequirement(
        id="A.8.30",
        category="Annex A",
        section="Technological Controls",
        name="Outsourced development",
        requirement="Development activities that have been outsourced shall be monitored and reviewed to ensure they meet security requirements."
    ),
    ControlRequirement(
        id="A.8.31",
        category="Annex A",
        section="Technological Controls",
        name="Separation of development, test and production environments",
        requirement="Secure, separate environments shall be maintained for development, testing and production to prevent unauthorised code changes."
    ),
    ControlRequirement(
        id="A.8.32",
        category="Annex A",
        section="Technological Controls",
        name="Change management",
        requirement="Procedures shall be implemented to manage changes to information processing facilities and information systems in a controlled manner."
    ),
    ControlRequirement(
        id="A.8.33",
        category="Annex A",
        section="Technological Controls",
        name="Test information",
        requirement="Information used for testing shall be appropriately selected, protected and managed to prevent unauthorised access and use."
    ),
    ControlRequirement(
        id="A.8.34",
        category="Annex A",
        section="Technological Controls",
        name="Protection of information systems during audit testing",
        requirement="Audit tests and other assurance activities on operational systems shall be appropriately planned and managed to minimise disruption."
    ),
]


# ============================================================================
# HELPER FUNCTIONS FOR FRAMEWORK ACCESS
# ============================================================================

def get_all_controls() -> List[ControlRequirement]:
    """Return all controls in the framework."""
    return ISO27001_FRAMEWORK


def get_controls_by_category(category: str) -> List[ControlRequirement]:
    """
    Filter controls by category.
    
    Args:
        category: "Clause" or "Annex A"
    
    Returns:
        List of controls matching the category
    """
    return [ctrl for ctrl in ISO27001_FRAMEWORK if ctrl.category == category]


def get_control_by_id(control_id: str) -> ControlRequirement | None:
    """
    Retrieve a single control by ID.
    
    Args:
        control_id: Control identifier (e.g., "A.5.15", "4.1")
    
    Returns:
        ControlRequirement if found, None otherwise
    """
    for ctrl in ISO27001_FRAMEWORK:
        if ctrl.id == control_id:
            return ctrl
    return None


def get_controls_by_section(section: str) -> List[ControlRequirement]:
    """
    Filter controls by section name.
    
    Args:
        section: Section name (e.g., "Organizational Controls", "Leadership")
    
    Returns:
        List of controls in the section
    """
    return [ctrl for ctrl in ISO27001_FRAMEWORK if ctrl.section == section]


def get_all_sections() -> set[str]:
    """Return all unique section names in the framework."""
    return {ctrl.section for ctrl in ISO27001_FRAMEWORK}


def get_framework_summary() -> dict:
    """
    Get a summary of the framework structure.
    
    Returns:
        Dictionary with counts and organization info
    """
    clauses = [c for c in ISO27001_FRAMEWORK if c.category == "Clause"]
    annex_a = [c for c in ISO27001_FRAMEWORK if c.category == "Annex A"]
    
    sections = {}
    for ctrl in ISO27001_FRAMEWORK:
        section = ctrl.section
        if section not in sections:
            sections[section] = []
        sections[section].append(ctrl.id)
    
    return {
        "total_controls": len(ISO27001_FRAMEWORK),
        "clauses": len(clauses),
        "annex_a_controls": len(annex_a),
        "unique_sections": len(set(ctrl.section for ctrl in ISO27001_FRAMEWORK)),
        "sections": sections,
    }


if __name__ == "__main__":
    # Example usage
    print("ISO 27001:2022 Framework Loaded")
    print("=" * 60)
    summary = get_framework_summary()
    print(f"Total Controls: {summary['total_controls']}")
    print(f"Clauses (4-10): {summary['clauses']}")
    print(f"Annex A Controls: {summary['annex_a_controls']}")
    print(f"Unique Sections: {summary['unique_sections']}")
    print("\nSections:")
    for section, controls in summary["sections"].items():
        print(f"  {section}: {len(controls)} controls")
    
    # Example: Get control A.5.15
    control = get_control_by_id("A.5.15")
    if control:
        print(f"\nExample Control: {control.id} - {control.name}")
        print(f"Requirement: {control.requirement}")
