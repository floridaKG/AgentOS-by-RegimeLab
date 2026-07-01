// Agent OS Neo4j Graph Schema
// Optional adapter for relationship-based memory

// Constraints
CREATE CONSTRAINT lesson_id_unique IF NOT EXISTS FOR (l:Lesson) REQUIRE l.id IS UNIQUE;
CREATE CONSTRAINT agent_id_unique IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE;

// Node labels
// :Lesson - A captured lesson, stumble, or decision
// :Agent - An agent that contributed lessons
// :Workspace - A workspace context
// :Topic - A subject area

// Relationships
// (a:Agent)-[:CONTRIBUTED]->(l:Lesson)
// (l:Lesson)-[:BELONGS_TO]->(w:Workspace)
// (l:Lesson)-[:ABOUT]->(t:Topic)
// (l:Lesson)-[:RELATES_TO]->(l2:Lesson)
