"""Build the routing graph from the noded OSM roads and pickle it -> data/graph.pkl"""
import pickle
import networkx as nx
from config import DATA
from graph import RoadGraph

g = RoadGraph(str(DATA / 'noded_roads.geojson'))
pickle.dump(g, open(DATA / 'graph.pkl', 'wb'))
print(f"{g.G.number_of_nodes()} nodes, {g.G.number_of_edges()} edges, {nx.number_connected_components(g.G)} components, "
      f"{g.joined} dangling ends joined")
