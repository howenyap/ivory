# Tutorial: Project Research and Development

## Instructions

- This project is a **group project**.
- The project is 20% of the total mark for the course.
- The details of the marking scheme will be communicated later.
- The estimated workload is 30 hours per member in total, or 6 hours per week for 5 weeks,
    per project member.
- Submit your paper by **Sunday, 12 April 2026, 23:59** to EasyChair.
- Submit your video by **Sunday, 12 April 2026, 23:59** to Canvas.
- Submit your reviews ( _individual submission_ ) by **Friday, 17 April 2026, 23:59** to Easy-
    Chair.

The University takes a strict view of plagiarism and considers it a serious form of academic
dishonesty. Any student found to have engaged in such misconduct will be subjected to disci-
plinary action by the University. Please refer to the NUS Plagiarism Policy. The University
prohibits cheating in any form during assessments, tests, quizzes or examinations. Such acts
will be considered, at minimum, as “Moderate” offences, resulting in the default sanction of a
‘Fail’ grade for the entire course.


## Topics

_Each group chooses one topic from the list below and indicates its choice in the GoogleSheet
indicated in Canvas._ **_At most, 3 groups can choose each topic on a first-come-first-
served basis_**.

1. **Entity-Relationship Graphical Interface.** Develop an interactive drawing tool fa-
    cilitating the creation of _Entity-Relationship Diagram_ ( _ERD_ ) and the corresponding _SQL_
    _DDL_ code generation. The tool supports various notations, including those from lectures
    ( _i.e., multiple candidate keys, etc_ ), UML, and logical diagrams. It allows conversion be-
    tween the different notations and support for multiple target DBMS and versions, accom-
    modating system-specific syntax and additional features. Development options include a
    service, a JavaScript applet, or a standalone software ( _e.g., in Python_ ), with potential
    Cloud service or virtual machine deployment.
2. **Provenance-Aware Relational Algebra.** Develop a provenance-aware relational al-
    gebra evaluator for a subset of relational algebra expressions ( _selection, projection, cross_
    _product, multiset sum, deduplication, and potentially aggregation_ ). The semantics is _mul-_
    _tiset_ semantics. Provenance tracking is done using _provenance semiring framework_ and
    includes Boolean function semiring to support probabilistic database. The project in-
    cludes benchmark to test the correctness of provenance tracking as well as to evaluate
    the performance of the evaluator ( _comparison with and without provenance_ ) alongside the
    implementation.
3. **Leaderboard.** Develop and online platform for SQL performance competitions, allow-
    ing users to submit queries and compete based on _correctness_ and _eﬀiciency_. The platform
    –implemented for PostgreSQL– features additional functionalities such as timeouts, mul-
    tiple database instance testing, and query parsing. Deployment options include a Cloud
    service or virtual machine deployment.
4. **Large Language Model Optimization of SQL Query.** Illustrate and evaluate
    the capabilities of large language model ( _LLM_ ) to rewrite complex SQL queries that
    suffers from slow executions despite query optimization. The research involves prompt
    engineering and the criteria that makes a query challenging for LLM to optimize. The
    evaluation ( _positive/negative_ ) is done on standard benchmark such as TPC benchmark
    ( _e.g., TPC-DS_ ) comparing the performance against other query rewriting tools ( _e.g.,_
    _pg_query_ ).
5. **Fake but Realistic Data.** Design, implement, and demostrate a tool for generating
    realistic random data for entity-relationship designs. The tool considers participation
    constraints, join selectivity, and probability distributions. The report and presentation
    cover background concepts such as cardinality, participation, and selectivity in relational
    database.
6. **Machine Learning for Cost Estimator.** Design, train, and comparatively evaluate
    machine learning models to estimate the cost, planning time, and execution time of SQL
    queries with PostgreSQL. Investigate opportunities to design a machine learning model
    assisting the formulation of eﬀicient queries.
7. **Text-Based Entity-Relationship Model.** Design a _declarative_ language to describe
    _Entity-Relationship Diagram_ ( _ERD-Language_ ) and another _declarative_ language to query
    the given ERD ( _ERD-Query_ ). The ERD-language supports the ERD notation from the
    lecture and the ERD-Query supports common constraints query on identification, partic-
    ipation, and relationship.


8. **Why-Not Explanations of Query Answers in PostgreSQL.** Develop a system
    ( _e.g., query rewriting, relational algebra, etc_ ) to explain why some data is missing from
    the output ( _i.e., Why-Not provenance_ ). The project includes benchmark to test the
    correctness of Why-Not explanation as well as to evaluate the performance of the evaluator
    ( _comparison with and without Why-Not analysis_ ) alongside the implementation.
9. **The Chase.** Create an interactive tool implementing the Chase algorithm for func-
    tional dependencies. The tool offers functionalities such as entailment, lossless decomposi-
    tion, and minimal cover generation. The project includes examples, benchmarks, and may
    offer multiple Chase algorithm versions ( _e.g., including multi-valued dependencies_ ). The
    report provides theoretical background coverage. Deployment options include a Cloud
    service or virtual machine deployment.
10. **Large Language Model for Database Design and Programming.** Illustrate and
evaluate the capabilities of large language model ( _LLM_ ) to answer database design and
programming questions. The questions may cover all or part of the syllabus of an intro-
ductory course on the design and implementation of database applications with relational
database systems and SQL for computing students. The topic includes: entity-relationship
modelling, SQL data definition, manipulation, and query languages, stored procedures and
triggers, as well as normalization. The research involves prompt engineering and the iden-
tification of criteria that makes a query easy or challenging for an LLM. The evaluation
involves testing the LLM capabilities with questions from at least one popular textbook
( _e.g., Database Management Systems by Ramakrishnan, Raghu, and Gehrke_ ).
11. **Relax and Find the Key.** Develop and online game centered around identifying
candidate keys of relational schemas with funcitonal dependencies. The game involves the
random generation of problems of different diﬀiculty levels ( _to be defined theoretically_ ).
Deployment options include a Cloud service or virtual machine deployment. The report
and presentation present the theoretical background and the game.
12. **Monte-Carlo Sampling Normalization.** Investigate the distribution of minimal
covers and normal forms of a relation with functional dependencies using Monte-Carlo
sampling techniques. The project involves understanding and implementing algorithms
for the uniform generation of sets of functional dependencies at random, the computation
of minimal covers, and the testing of normal forms.
13. **Check Constraints Compiler.** Design and implement a PostgreSQL compiler that
translatesCHECKSQL constraints into _triggers_ and _stored procedures_. The project includes
performance evaluation alongside the implementation.


## Paper

Your work and results are presented in a paper. The paper’s submission is managed as a
scientific and technical conference. The paper consists of six (6) sections, followed by a list of
references.

1. The _Title_ summarizes in a few words the main idea of the work.
2. The _Abstract_ overviews in a few lines, the motivation and the work. It also announces the
    main result or results.
3. The _Introduction_ section presents the challenge and outlines the work.
4. The _Background_ section presents the domain and technical textbook knowledge necessary
    to understand the paper.
5. The _Related Work_ section surveys the related work in order to justify the choice of the
    selected technique.
6. The _Methodology_ section presents the selected technique.
7. The _Performance Evaluation_ section presents the experimental set-up, including data
    sets and metrics, as well as presents and analyzes the results of the comparative empirical
    performance evaluation.
8. The _Conclusion_ section summarizes the work and results.
9. The _References_ lists the sources cited in the paper.

The paper is no longer than fifteen (15) pages, including figures and references, in Portable
Document Format (.pdf). The paper is written in LaTeX^1 using Overleaf^2 (www.overleaf.
com) and follows Springer Lecture Notes in Computer Science’s template. The group leader
submits the paper to the CS4221/CS5421 conference created for this purpose in EasyChair^3
(easychair.org). You will receive an invitation toeasychair.organd to the CS4221/CS
program committee in due course.

## Video

The video summarizes the work and results as would the presentation of a paper in a scientific
and technical conference.

1. The video consists of slides and comments.
2. The video follows the same structure as the report.
3. The video may include other relevant content such as demostrations of the model.
4. The video must be in MP4 (.mp4) or in QuickTime (.mov) file format no longer than 10
    minutes and no larger than 200MB.

You are not allowed to artificially speed the video but you may usehandbrake.frto reduce
the file size, if needed.

(^1) LaTeX is a typesetting system widely used for scientific and technical writing.
(^2) Overleaf is an online collaborative platform for LaTeX document creation. Overleaf has a user-friendly
interface that simplifies LaTeX usage, enables real-time collaboration and facilitates access to various templates
and tools.
(^3) EasyChair is an online conference management system designed to streamline the submission and review
process.


## Reviews

The project evaluation is managed as a scientific and technical conference.

1. Each student is assigned to review 3 papers.
2. Download the papers assigned to you in CS4221/CS5421 conference in EasyChair.
3. Read and review the papers following the guidelines that will be communicated to you.
4. Submit your reviews to the CS4221/CS5421 conference in EasyChair.



