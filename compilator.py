from pysmi.codegen import PySnmpCodeGen
from pysmi.compiler import MibCompiler
from pysmi.parser import SmiV1CompatParser
from pysmi.reader.localfile import FileReader
from pysmi.searcher.stub import StubSearcher
from pysmi.writer.localfile import FileWriter
from pysmi import debug

# Enable debugging
debug.setLogger(debug.Debug('reader', 'compiler'))

inputMib = 'NETPING-MIB.mib'
outputDir = 'mibs/compiled'
mibSourceDir = '/usr/share/snmp/mibs/ietf'

# Initialize MIB compiler
compiler = MibCompiler(
    SmiV1CompatParser(),
    PySnmpCodeGen(),
    FileWriter(outputDir)
)

# Set MIB source directories
compiler.addSources(FileReader(mibSourceDir))

# Add a stub searcher for already compiled MIBs (optional)
compiler.addSearchers(StubSearcher())

# Compile MIB
results = compiler.compile(inputMib)

print(results)